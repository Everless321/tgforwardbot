import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, func, select

from app.core.database import async_session
from app.models.message import ForwardRule, MessageLog
from app.schemas.rule import RuleCreate, RuleResponse, RuleUpdate
from app.telegram.handlers import register_handlers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rules", tags=["rules"])


async def _rule_with_count(rule: ForwardRule, session) -> RuleResponse:
    result = await session.execute(
        select(func.count()).where(MessageLog.rule_id == rule.id)
    )
    count = result.scalar_one()
    filters = json.loads(rule.filters) if rule.filters else None
    return RuleResponse(
        id=rule.id,
        source_chat_id=rule.source_chat_id,
        target_chat_id=rule.target_chat_id,
        enabled=rule.enabled,
        filters=filters,
        sync_status=rule.sync_status.value,
        synced_msg_count=rule.synced_msg_count,
        created_at=rule.created_at,
        message_count=count,
    )


async def _rebuild_handlers(app) -> None:
    from app.main import load_rules_from_db

    rule_map = await load_rules_from_db()
    app.state.rule_map = rule_map

    client = getattr(app.state, "tg_client", None)
    forwarder = getattr(app.state, "forwarder", None)
    if client and forwarder:
        register_handlers(client, rule_map, forwarder)


@router.get("/", response_model=list[RuleResponse])
async def list_rules():
    async with async_session() as session:
        result = await session.execute(select(ForwardRule))
        rules = result.scalars().all()
        return [await _rule_with_count(r, session) for r in rules]


@router.post("/", response_model=RuleResponse, status_code=201)
async def create_rule(body: RuleCreate, request: Request):
    async with async_session() as session:
        existing = await session.execute(
            select(ForwardRule).where(
                ForwardRule.source_chat_id == body.source_chat_id,
                ForwardRule.target_chat_id == body.target_chat_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Rule already exists")

        rule = ForwardRule(
            source_chat_id=body.source_chat_id,
            target_chat_id=body.target_chat_id,
            filters=json.dumps(body.filters) if body.filters else None,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)

    await _rebuild_handlers(request.app)

    async with async_session() as session:
        r = await session.get(ForwardRule, rule.id)
        return await _rule_with_count(r, session)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: int, body: RuleUpdate, request: Request):
    async with async_session() as session:
        rule = await session.get(ForwardRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        if body.enabled is not None:
            rule.enabled = body.enabled
        if body.filters is not None:
            rule.filters = json.dumps(body.filters)

        await session.commit()
        await session.refresh(rule)
        resp = await _rule_with_count(rule, session)

    await _rebuild_handlers(request.app)
    return resp


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, request: Request):
    async with async_session() as session:
        rule = await session.get(ForwardRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        await session.execute(
            delete(MessageLog).where(MessageLog.rule_id == rule_id)
        )
        await session.delete(rule)
        await session.commit()

    await _rebuild_handlers(request.app)


@router.post("/{rule_id}/sync")
async def start_sync(rule_id: int, request: Request):
    async with async_session() as session:
        rule = await session.get(ForwardRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

    syncer = getattr(request.app.state, "syncer", None)
    if not syncer:
        raise HTTPException(status_code=503, detail="Syncer not initialized")

    started = syncer.start_sync(rule_id)
    if not started:
        raise HTTPException(status_code=409, detail="Sync already running")

    return {"status": "started", "rule_id": rule_id}


@router.post("/{rule_id}/sync/stop")
async def stop_sync(rule_id: int, request: Request):
    from app.models.message import SyncStatus

    syncer = getattr(request.app.state, "syncer", None)
    if not syncer:
        raise HTTPException(status_code=503, detail="Syncer not initialized")

    stopped = syncer.stop_sync(rule_id)

    # 即使内存中没有任务，也将数据库状态重置为 IDLE（处理重启后残留状态）
    if not stopped:
        async with async_session() as session:
            rule = await session.get(ForwardRule, rule_id)
            if rule and rule.sync_status == SyncStatus.SYNCING:
                rule.sync_status = SyncStatus.IDLE
                await session.commit()
                return {"status": "stopped", "rule_id": rule_id}
            raise HTTPException(status_code=409, detail="No sync running for this rule")

    return {"status": "stopped", "rule_id": rule_id}
