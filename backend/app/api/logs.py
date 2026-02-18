from fastapi import APIRouter

from app.core.log_buffer import log_buffer

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/logs")
async def get_logs(limit: int = 200, level: str | None = None):
    return log_buffer.get_entries(limit=min(limit, 500), level=level)
