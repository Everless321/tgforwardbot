import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import event_bus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
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
