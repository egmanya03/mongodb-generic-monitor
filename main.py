"""
main.py
Generic MongoDB Query Service — with saved automations.

Features:
  - Kisi bhi MongoDB profile pe query chalao (read/write)
  - Query result ko image (table/card) me convert karo
  - Image ko Matrix room me bhejo
  - Queries ko "save" karke schedule pe daalo — service khud
    chalayegi, image banayegi, Matrix pe bhejegi, bina manual click ke
  - UI se hi naye DB profiles add/delete karo

Modules:
    config.py          -> config.yaml (DB profiles, Matrix settings)
    database.py        -> multiple MongoDB profiles manage karta hai
    image_export.py     -> table/card image banata hai
    matrix_client.py    -> Matrix room me image bhejta hai
    saved_queries.py    -> automations ka persistent storage
    scheduler.py         -> background scheduling (APScheduler)

Run: uvicorn main:app --reload
Docs: http://localhost:8000/docs
"""

import base64
import json
from typing import Any, Optional

from bson import ObjectId
from bson.json_util import default as bson_default
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from database import get_db, check_connection
from image_export import generate_table_image, generate_card_image
from matrix_client import send_image_to_matrix, MatrixError
import saved_queries as sq_store
import scheduler as sched

app = FastAPI(
    title="Generic MongoDB Query Service",
    description="Multiple MongoDB profiles, image export, Matrix integration, aur scheduled automations.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def to_json_safe(data: Any) -> Any:
    return json.loads(json.dumps(data, default=bson_default))


def resolve_id_filter(doc_id: str) -> dict:
    if ObjectId.is_valid(doc_id):
        return {"_id": ObjectId(doc_id)}
    return {"_id": doc_id}


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, settings.max_limit))


def _run_find_or_aggregate(db, collection: str, operation: str, filter: dict = None,
                            projection: dict = None, sort: list = None,
                            pipeline: list = None, limit: int = None) -> list:
    if operation == "aggregate":
        return list(db[collection].aggregate(pipeline or []))
    cursor = db[collection].find(filter or {}, projection)
    if sort:
        cursor = cursor.sort(sort)
    cursor = cursor.limit(clamp_limit(limit or settings.default_limit))
    return list(cursor)


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class QueryRequest(BaseModel):
    filter: dict = {}
    projection: Optional[dict] = None
    sort: Optional[list] = None
    skip: int = 0
    limit: int = None


class AggregateRequest(BaseModel):
    pipeline: list


class InsertRequest(BaseModel):
    documents: list


class UpdateRequest(BaseModel):
    filter: dict
    update: dict
    many: bool = False


class DeleteRequest(BaseModel):
    filter: dict
    many: bool = False


class ProfileSwitchRequest(BaseModel):
    profile: str


class ProfileCreateRequest(BaseModel):
    name: str
    mongo_uri: str
    db_name: str
    requires_vpn: bool = False
    label: Optional[str] = None


class ImageRequest(BaseModel):
    data: list
    columns: Optional[list] = None
    image_type: str
    title: str = ""


class MatrixSendRequest(BaseModel):
    image_base64: str
    filename: str = "query_result.png"
    caption: Optional[str] = None
    room_id: Optional[str] = None


class SavedQueryRequest(BaseModel):
    name: str
    profile: str
    collection: str
    operation: str = "find"          # "find" | "aggregate"
    filter: dict = {}
    projection: Optional[dict] = None
    sort: Optional[list] = None
    pipeline: list = []
    image_type: str = "table"
    columns: Optional[list] = None
    title: Optional[str] = None
    matrix_room_id: Optional[str] = None
    caption: Optional[str] = None
    schedule_type: str = "interval"  # "interval" | "daily" | "manual"
    schedule_minutes: int = 0        # interval type ke liye (0 = manual)
    run_at_time: Optional[str] = None  # daily type ke liye, "HH:MM" 24hr format
    enabled: bool = True


# ------------------------------------------------------------------
# Health / profile management
# ------------------------------------------------------------------

@app.get("/")
def health_check(profile: Optional[str] = None):
    target = profile or settings.active_profile
    connected = check_connection(target)
    prof = settings.get_profile(target)
    return {
        "status": "ok" if connected else "mongo_unreachable",
        "active_profile": target,
        "database": prof["db_name"],
        "requires_vpn": prof.get("requires_vpn", False),
    }


@app.get("/profiles")
def list_profiles():
    """Sab DB profiles, connection status, aur unpe kitni active (scheduled) automations hain."""
    all_queries = sq_store.list_queries()
    result = []
    for name, p in settings.profiles.items():
        active_count = sum(
            1 for q in all_queries
            if q["profile"] == name and q.get("enabled") and q.get("schedule_minutes", 0) > 0
        )
        result.append({
            "name": name,
            "label": p.get("label", name),
            "db_name": p["db_name"],
            "requires_vpn": p.get("requires_vpn", False),
            "connected": check_connection(name),
            "active_automations": active_count,
        })
    return {"active_profile": settings.active_profile, "profiles": result}


@app.post("/profiles/switch")
def switch_profile(body: ProfileSwitchRequest):
    try:
        settings.set_active_profile(body.profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"active_profile": body.profile, "connected": check_connection(body.profile)}


@app.post("/profiles")
def create_profile(body: ProfileCreateRequest):
    """Naya MongoDB database profile add karo — config.yaml me permanently save hota hai."""
    if body.name in settings.profiles:
        raise HTTPException(status_code=400, detail=f"Profile '{body.name}' pehle se maujood hai")
    settings.add_profile(body.name, body.mongo_uri, body.db_name, body.requires_vpn, body.label)
    return {"status": "created", "name": body.name, "connected": check_connection(body.name)}


@app.delete("/profiles/{name}")
def remove_profile(name: str):
    try:
        settings.delete_profile(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Us profile se juri automations bhi unschedule kar do
    for q in sq_store.list_queries():
        if q["profile"] == name:
            sched.unschedule_query(q["id"])
    return {"status": "deleted", "name": name}


@app.get("/collections")
def list_collections(profile: Optional[str] = None):
    db = get_db(profile)
    return {"database": settings.get_profile(profile)["db_name"], "collections": db.list_collection_names()}


# ------------------------------------------------------------------
# Saved Queries (Automations)
# ------------------------------------------------------------------

def execute_saved_query(query_id: str):
    """
    Ek saved query ko poora execute karta hai: DB se data laata hai,
    image banata hai, Matrix pe bhejta hai. Scheduler aur "Run now"
    dono isi function ko call karte hain.
    """
    q = sq_store.get_query(query_id)
    if not q or not q.get("enabled"):
        return

    try:
        db = get_db(q["profile"])
        data = _run_find_or_aggregate(
            db, q["collection"], q["operation"],
            filter=q.get("filter"), projection=q.get("projection"),
            sort=q.get("sort"), pipeline=q.get("pipeline"),
        )
        data = to_json_safe(data)

        if not data:
            sq_store.record_run_result(query_id, "success", "Query ne 0 documents diye — image nahi bani")
            return

        if q["image_type"] == "table":
            columns = q.get("columns") or list(data[0].keys())
            img_bytes = generate_table_image(data, columns, q.get("title") or q["name"])
        else:
            img_bytes = generate_card_image(data[0], q.get("title") or q["name"])

        matrix_cfg = settings.matrix
        room_id = q.get("matrix_room_id") or matrix_cfg.get("default_room_id")
        send_image_to_matrix(
            image_bytes=img_bytes,
            filename=f"{q['name'].replace(' ', '_')}.png",
            homeserver=matrix_cfg.get("homeserver", ""),
            access_token=matrix_cfg.get("access_token", ""),
            room_id=room_id,
            caption=q.get("caption") or q["name"],
        )
        sq_store.record_run_result(query_id, "success", f"{len(data)} documents processed, image sent")
    except Exception as e:
        sq_store.record_run_result(query_id, "error", str(e))


@app.get("/saved-queries")
def list_saved_queries():
    return {"queries": sq_store.list_queries()}


@app.post("/saved-queries")
def create_saved_query(body: SavedQueryRequest):
    if body.profile not in settings.profiles:
        raise HTTPException(status_code=404, detail=f"Profile '{body.profile}' nahi mila")
    q = sq_store.add_query(body.model_dump())
    if q["enabled"]:
        sched.schedule_query(q["id"], q["schedule_type"], execute_saved_query,
                              minutes=q.get("schedule_minutes"), run_at_time=q.get("run_at_time"))
    return q


@app.put("/saved-queries/{query_id}")
def edit_saved_query(query_id: str, body: SavedQueryRequest):
    q = sq_store.update_query(query_id, body.model_dump())
    if not q:
        raise HTTPException(status_code=404, detail="Saved query nahi mili")
    if q["enabled"]:
        sched.schedule_query(query_id, q["schedule_type"], execute_saved_query,
                              minutes=q.get("schedule_minutes"), run_at_time=q.get("run_at_time"))
    else:
        sched.unschedule_query(query_id)
    return q


@app.delete("/saved-queries/{query_id}")
def remove_saved_query(query_id: str):
    sched.unschedule_query(query_id)
    ok = sq_store.delete_query(query_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Saved query nahi mili")
    return {"status": "deleted", "id": query_id}


@app.post("/saved-queries/{query_id}/run-now")
def run_saved_query_now(query_id: str):
    q = sq_store.get_query(query_id)
    if not q:
        raise HTTPException(status_code=404, detail="Saved query nahi mili")
    execute_saved_query(query_id)
    return sq_store.get_query(query_id)


@app.on_event("startup")
def on_startup():
    """Service start hote hi sab enabled automations ko schedule kar do (interval ya daily)."""
    for q in sq_store.list_queries():
        if q.get("enabled") and q.get("schedule_type") in ("interval", "daily"):
            sched.schedule_query(q["id"], q["schedule_type"], execute_saved_query,
                                  minutes=q.get("schedule_minutes"), run_at_time=q.get("run_at_time"))


# ------------------------------------------------------------------
# Generic read endpoints
# ------------------------------------------------------------------

@app.get("/{collection}")
def get_documents(
    collection: str,
    filter: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: int = Query(1),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    profile: Optional[str] = None,
):
    db = get_db(profile)
    if collection not in db.list_collection_names():
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")

    query_filter = {}
    if filter:
        try:
            query_filter = json.loads(filter)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="filter must be valid JSON")

    effective_limit = clamp_limit(limit or settings.default_limit)
    cursor = db[collection].find(query_filter).skip(skip).limit(effective_limit)
    if sort_by:
        cursor = cursor.sort(sort_by, sort_order)

    results = list(cursor)
    return JSONResponse(content={"count": len(results), "data": to_json_safe(results)})


@app.get("/{collection}/{doc_id}")
def get_document_by_id(collection: str, doc_id: str, profile: Optional[str] = None):
    db = get_db(profile)
    if collection not in db.list_collection_names():
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    doc = db[collection].find_one(resolve_id_filter(doc_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return JSONResponse(content=to_json_safe(doc))


@app.post("/{collection}/query")
def query_documents(collection: str, body: QueryRequest, profile: Optional[str] = None):
    db = get_db(profile)
    if collection not in db.list_collection_names():
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")

    cursor = db[collection].find(body.filter, body.projection)
    if body.sort:
        cursor = cursor.sort(body.sort)
    effective_limit = clamp_limit(body.limit or settings.default_limit)
    cursor = cursor.skip(body.skip).limit(effective_limit)

    results = list(cursor)
    return JSONResponse(content={"count": len(results), "data": to_json_safe(results)})


@app.post("/{collection}/aggregate")
def aggregate_documents(collection: str, body: AggregateRequest, profile: Optional[str] = None):
    db = get_db(profile)
    if collection not in db.list_collection_names():
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    try:
        results = list(db[collection].aggregate(body.pipeline))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Aggregation error: {str(e)}")
    return JSONResponse(content={"count": len(results), "data": to_json_safe(results)})


# ------------------------------------------------------------------
# Write endpoints
# ------------------------------------------------------------------

@app.post("/{collection}/insert")
def insert_documents(collection: str, body: InsertRequest, profile: Optional[str] = None):
    db = get_db(profile)
    if not body.documents:
        raise HTTPException(status_code=400, detail="documents list khaali nahi ho sakti")
    try:
        result = db[collection].insert_many(body.documents)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Insert error: {str(e)}")
    return JSONResponse(content={
        "inserted_count": len(result.inserted_ids),
        "inserted_ids": to_json_safe(result.inserted_ids),
    })


@app.patch("/{collection}/update")
def update_documents(collection: str, body: UpdateRequest, profile: Optional[str] = None):
    db = get_db(profile)
    if collection not in db.list_collection_names():
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    try:
        if body.many:
            result = db[collection].update_many(body.filter, body.update)
        else:
            result = db[collection].update_one(body.filter, body.update)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Update error: {str(e)}")
    return JSONResponse(content={"matched_count": result.matched_count, "modified_count": result.modified_count})


@app.delete("/{collection}/delete")
def delete_documents(collection: str, body: DeleteRequest, profile: Optional[str] = None):
    db = get_db(profile)
    if collection not in db.list_collection_names():
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
    if body.many and not body.filter:
        raise HTTPException(status_code=400, detail="Safety check: many=true ke saath khaali filter allowed nahi.")
    try:
        if body.many:
            result = db[collection].delete_many(body.filter)
        else:
            result = db[collection].delete_one(body.filter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Delete error: {str(e)}")
    return JSONResponse(content={"deleted_count": result.deleted_count})


# ------------------------------------------------------------------
# Image export
# ------------------------------------------------------------------

@app.post("/image/generate")
def generate_image(body: ImageRequest):
    if not body.data:
        raise HTTPException(status_code=400, detail="data khaali hai — pehle query chalayein")
    try:
        if body.image_type == "table":
            columns = body.columns or list(body.data[0].keys())
            img_bytes = generate_table_image(body.data, columns, body.title)
        elif body.image_type == "card":
            img_bytes = generate_card_image(body.data[0], body.title)
        else:
            raise HTTPException(status_code=400, detail="image_type 'table' ya 'card' hona chahiye")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    encoded = base64.b64encode(img_bytes).decode("utf-8")
    return {"image_base64": encoded, "mime_type": "image/png"}


# ------------------------------------------------------------------
# Matrix
# ------------------------------------------------------------------

@app.post("/matrix/send")
def matrix_send(body: MatrixSendRequest):
    matrix_cfg = settings.matrix
    room_id = body.room_id or matrix_cfg.get("default_room_id")
    try:
        image_bytes = base64.b64decode(body.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="image_base64 valid base64 nahi hai")
    try:
        result = send_image_to_matrix(
            image_bytes=image_bytes, filename=body.filename,
            homeserver=matrix_cfg.get("homeserver", ""), access_token=matrix_cfg.get("access_token", ""),
            room_id=room_id, caption=body.caption,
        )
    except MatrixError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "sent", **result}
