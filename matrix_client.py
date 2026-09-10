"""
matrix_client.py
Matrix homeserver ke Client-Server API se directly baat karta hai
(koi heavy SDK nahi, sirf 'requests' library) — image upload karke
kisi room me bhejne ke liye.

Zaroori config (config.yaml me "matrix:" section):
    homeserver       -> e.g. https://matrix.org
    access_token     -> bot/account ka access token
    default_room_id  -> jaise "!abcdefgh:matrix.org"

Access token kaise milta hai:
    Element app -> Settings -> Help & About -> Advanced ->
    "Access Token" (ya apne bot account se login karke API se le sakte ho)
"""

import requests


class MatrixError(Exception):
    pass


def send_image_to_matrix(
    image_bytes: bytes,
    filename: str,
    homeserver: str,
    access_token: str,
    room_id: str,
    caption: str = None,
) -> dict:
    """
    Image ko Matrix homeserver pe upload karta hai, phir diye gaye
    room me bhejta hai. Do steps hote hain Matrix protocol me:
      1. Media upload -> content URI milta hai (mxc://...)
      2. Room me message event bhejna, us URI ke saath
    """
    if not access_token:
        raise MatrixError("matrix.access_token config.yaml me set nahi hai")
    if not room_id:
        raise MatrixError("room_id nahi diya gaya aur config.yaml me default_room_id bhi khaali hai")

    headers = {"Authorization": f"Bearer {access_token}"}

    # ---- Step 1: Upload media ----
    upload_url = f"{homeserver}/_matrix/media/v3/upload"
    upload_headers = {**headers, "Content-Type": "image/png"}
    upload_res = requests.post(
        upload_url,
        headers=upload_headers,
        params={"filename": filename},
        data=image_bytes,
        timeout=15,
    )
    if upload_res.status_code != 200:
        raise MatrixError(f"Media upload fail hua: {upload_res.status_code} {upload_res.text}")

    content_uri = upload_res.json().get("content_uri")
    if not content_uri:
        raise MatrixError("Upload response me content_uri nahi mila")

    # ---- Step 2: Send message to room ----
    import time
    txn_id = str(int(time.time() * 1000))
    send_url = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"

    body = {
        "msgtype": "m.image",
        "body": caption or filename,
        "url": content_uri,
        "info": {"mimetype": "image/png", "size": len(image_bytes)},
    }
    send_res = requests.put(send_url, headers=headers, json=body, timeout=15)

    if send_res.status_code != 200:
        raise MatrixError(f"Room me bhejne me error: {send_res.status_code} {send_res.text}")

    return {"event_id": send_res.json().get("event_id"), "content_uri": content_uri}
