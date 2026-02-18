import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import event_bus
from app.core.security import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


def _extract_bearer_token(websocket: WebSocket) -> str | None:
    auth = websocket.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None

    # Fallback for clients that can't set headers easily.
    token = websocket.query_params.get("token")
    return token.strip() if token else None


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    token = _extract_bearer_token(websocket)
    if not token:
        await websocket.close(code=1008)
        return

    try:
        verify_token(token)
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    q = event_bus.subscribe()
    try:
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        event_bus.unsubscribe(q)
