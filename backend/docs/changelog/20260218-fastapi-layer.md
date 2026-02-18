# FastAPI API Layer — 2026-02-18

## Task

Build the FastAPI API layer on top of the existing Telethon forwarding engine.

## Todo

- [x] Create `app/core/events.py` — asyncio-based EventBus for WebSocket broadcast
- [x] Create `app/schemas/rule.py` — RuleCreate, RuleUpdate, RuleResponse
- [x] Create `app/schemas/message.py` — MessageResponse, MessageListResponse, StatusResponse
- [x] Create `app/api/rules.py` — CRUD router at `/api/rules`
- [x] Create `app/api/messages.py` — List router at `/api/messages`
- [x] Create `app/api/status.py` — Status endpoint at `/api/status`
- [x] Create `app/api/websocket.py` — WebSocket at `/ws/events`
- [x] Modify `app/telegram/forwarder.py` — publish events after each forward
- [x] Rewrite `app/main.py` — FastAPI + Telethon lifespan, CORS, routers

## Result

All 12 routes registered and imports verified:

- `GET  /api/rules/`
- `POST /api/rules/`
- `PUT  /api/rules/{rule_id}`
- `DELETE /api/rules/{rule_id}`
- `GET  /api/messages/`
- `GET  /api/messages/{rule_id}`
- `GET  /api/status`
- `WS   /ws/events`
- `GET  /openapi.json`, `/docs`, `/redoc`

Entry point: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
