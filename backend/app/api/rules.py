import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

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
        created_at=rule.created_at,
        message_count=count,
    )


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

    rule_map: dict = getattr(request.app.state, "rule_map", {})
    rule_map.setdefault(rule.source_chat_id, []).append((rule.target_chat_id, rule.id))

    client = getattr(request.app.state, "tg_client", None)
    forwarder = getattr(request.app.state, "forwarder", None)
    if client and forwarder:
        register_handlers(client, rule_map, forwarder)

    async with async_session() as session:
        r = await session.get(ForwardRule, rule.id)
        return await _rule_with_count(r, session)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: int, body: RuleUpdate):
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
        return await _rule_with_count(rule, session)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, request: Request):
    async with async_session() as session:
        rule = await session.get(ForwardRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        source_id = rule.source_chat_id
        target_id = rule.target_chat_id
        await session.delete(rule)
        await session.commit()

    rule_map: dict = getattr(request.app.state, "rule_map", {})
    targets = rule_map.get(source_id, [])
    rule_map[source_id] = [(t, rid) for t, rid in targets if rid != rule_id]
    if not rule_map[source_id]:
        del rule_map[source_id]

    _ = target_id
