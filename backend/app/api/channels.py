import json
import time

from fastapi import APIRouter, HTTPException, Query, Request
from telethon.tl.types import Channel, Chat

router = APIRouter(prefix="/api/channels", tags=["channels"])

_cache: dict = {"data": None, "ts": 0}
CACHE_TTL = 300


@router.get("/")
async def list_channels(request: Request, refresh: bool = Query(False)):
    client = getattr(request.app.state, "tg_client", None)
    if not client or not await client.is_user_authorized():
        raise HTTPException(status_code=401, detail="Not authenticated")

    now = time.time()
    if not refresh and _cache["data"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    result = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            result.append({
                "id": dialog.id,
                "title": dialog.title,
                "type": "channel" if isinstance(entity, Channel) and not entity.megagroup else "group",
                "username": getattr(entity, "username", None),
            })

    result.sort(key=lambda c: c["title"].lower())
    _cache["data"] = result
    _cache["ts"] = now
    return result
