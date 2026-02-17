from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.database import async_session
from app.models.message import MessageLog, MessageStatus
from app.schemas.message import MessageListResponse, MessageResponse

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("/", response_model=MessageListResponse)
async def list_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: MessageStatus | None = None,
    rule_id: int | None = None,
):
    async with async_session() as session:
        q = select(MessageLog)
        if status:
            q = q.where(MessageLog.status == status)
        if rule_id:
            q = q.where(MessageLog.rule_id == rule_id)

        total_result = await session.execute(select(func.count()).select_from(q.subquery()))
        total = total_result.scalar_one()

        q = q.order_by(MessageLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        items = result.scalars().all()

        return MessageListResponse(
            items=[MessageResponse.model_validate(m) for m in items],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/{rule_id}", response_model=MessageListResponse)
async def list_messages_by_rule(
    rule_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with async_session() as session:
        q = select(MessageLog).where(MessageLog.rule_id == rule_id)

        total_result = await session.execute(select(func.count()).select_from(q.subquery()))
        total = total_result.scalar_one()

        q = q.order_by(MessageLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        items = result.scalars().all()

        return MessageListResponse(
            items=[MessageResponse.model_validate(m) for m in items],
            total=total,
            page=page,
            page_size=page_size,
        )
