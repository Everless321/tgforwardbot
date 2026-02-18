import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.auth import router as auth_router
from app.api.channels import router as channels_router
from app.api.messages import router as messages_router
from app.api.rules import router as rules_router
from app.api.status import router as status_router
from app.api.websocket import router as ws_router
from app.core.config import settings
from app.core.database import Base, async_session, engine
from app.models.message import ForwardRule
from app.telegram.client import create_client
from app.telegram.forwarder import MessageForwarder
from app.telegram.handlers import register_handlers
from app.telegram.syncer import HistorySyncer

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def load_rules_from_db() -> dict[int, list[tuple[int, int]]]:
    rule_map: dict[int, list[tuple[int, int]]] = {}

    async with async_session() as session:
        result = await session.execute(
            select(ForwardRule).where(ForwardRule.enabled == True)  # noqa: E712
        )
        for rule in result.scalars().all():
            rule_map.setdefault(rule.source_chat_id, []).append(
                (rule.target_chat_id, rule.id)
            )

    return rule_map


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    client = create_client()
    forwarder = MessageForwarder(client, async_session)
    syncer = HistorySyncer(client, forwarder, async_session)
    await client.connect()

    app.state.tg_client = client
    app.state.forwarder = forwarder
    app.state.syncer = syncer
    app.state.rule_map = {}

    if await client.is_user_authorized():
        rule_map = await load_rules_from_db()
        register_handlers(client, rule_map, forwarder)
        app.state.rule_map = rule_map
        logger.info("TG Forward Bot started. Monitoring %d source channels.", len(rule_map))
    else:
        logger.info("TG Forward Bot started. Waiting for web UI authentication.")

    yield

    await client.disconnect()
    logger.info("TG Forward Bot stopped.")


app = FastAPI(title="TG Forward Bot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(channels_router)
app.include_router(rules_router)
app.include_router(messages_router)
app.include_router(status_router)
app.include_router(ws_router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=False)
