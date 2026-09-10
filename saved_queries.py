"""
saved_queries.py
"Saved queries" (automations) ka persistent storage — saved_queries.yaml
file me. Har saved query ek DB profile + collection + filter/pipeline +
image settings + Matrix room + schedule ka combination hoti hai.

UI se Add/Edit/Delete karne pe yahi file update hoti hai.
"""

import uuid
from pathlib import Path
from typing import Optional
import yaml

STORE_PATH = Path(__file__).parent / "saved_queries.yaml"


def _load() -> list:
    if not STORE_PATH.exists():
        return []
    with open(STORE_PATH, "r") as f:
        data = yaml.safe_load(f)
        return data or []


def _save(queries: list):
    with open(STORE_PATH, "w") as f:
        yaml.safe_dump(queries, f, sort_keys=False, allow_unicode=True)


def list_queries() -> list:
    return _load()


def get_query(query_id: str) -> Optional[dict]:
    for q in _load():
        if q["id"] == query_id:
            return q
    return None


def add_query(data: dict) -> dict:
    queries = _load()
    new_query = {
        "id": str(uuid.uuid4())[:8],
        "name": data["name"],
        "profile": data["profile"],
        "collection": data["collection"],
        "operation": data.get("operation", "find"),      # "find" ya "aggregate"
        "filter": data.get("filter", {}),
        "projection": data.get("projection"),
        "sort": data.get("sort"),
        "pipeline": data.get("pipeline", []),
        "image_type": data.get("image_type", "table"),
        "columns": data.get("columns"),
        "title": data.get("title", data["name"]),
        "matrix_room_id": data.get("matrix_room_id"),
        "caption": data.get("caption"),
        "schedule_type": data.get("schedule_type", "interval"),  # "interval" | "daily" | "manual"
        "schedule_minutes": data.get("schedule_minutes", 0),      # interval type ke liye
        "run_at_time": data.get("run_at_time"),                   # daily type ke liye, "HH:MM"
        "enabled": data.get("enabled", True),
        "last_run_at": None,
        "last_run_status": None,
        "last_run_message": None,
    }
    queries.append(new_query)
    _save(queries)
    return new_query


def update_query(query_id: str, data: dict) -> Optional[dict]:
    queries = _load()
    for i, q in enumerate(queries):
        if q["id"] == query_id:
            q.update({k: v for k, v in data.items() if k != "id"})
            queries[i] = q
            _save(queries)
            return q
    return None


def delete_query(query_id: str) -> bool:
    queries = _load()
    filtered = [q for q in queries if q["id"] != query_id]
    if len(filtered) == len(queries):
        return False
    _save(filtered)
    return True


def record_run_result(query_id: str, status: str, message: str = ""):
    """Query chalne ke baad last_run status update karta hai (scheduler se call hota hai)."""
    import datetime
    queries = _load()
    for q in queries:
        if q["id"] == query_id:
            q["last_run_at"] = datetime.datetime.utcnow().isoformat() + "Z"
            q["last_run_status"] = status
            q["last_run_message"] = message
    _save(queries)
