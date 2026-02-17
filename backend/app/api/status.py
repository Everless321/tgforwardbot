from datetime import datetime, timezone

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.database import async_session
from app.models.message import ForwardRule, MessageLog, MessageStatus
from app.schemas.message import StatusResponse

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request):
    client = getattr(request.app.state, "tg_client", None)
    connected = client is not None and client.is_connected()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session() as session:
        rules_count = (await session.execute(select(func.count()).select_from(ForwardRule))).scalar_one()
        rules_active = (
            await session.execute(
                select(func.count()).where(ForwardRule.enabled == True)  # noqa: E712
            )
        ).scalar_one()

        messages_today = (
            await session.execute(
                select(func.count()).where(MessageLog.created_at >= today_start)
            )
        ).scalar_one()

        messages_failed_today = (
            await session.execute(
                select(func.count()).where(
                    MessageLog.status == MessageStatus.FAILED,
                    MessageLog.created_at >= today_start,
                )
            )
        ).scalar_one()

        last_row = (
            await session.execute(
                select(MessageLog.created_at)
                .where(MessageLog.status == MessageStatus.SUCCESS)
                .order_by(MessageLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    return StatusResponse(
        connected=connected,
        rules_count=rules_count,
        rules_active=rules_active,
        messages_today=messages_today,
        messages_failed_today=messages_failed_today,
        last_forward_at=last_row,
    )
