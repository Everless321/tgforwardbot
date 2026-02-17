from datetime import datetime

from pydantic import BaseModel

from app.models.message import ContentType, MessageStatus


class MessageResponse(BaseModel):
    id: int
    rule_id: int
    source_msg_id: int
    target_msg_id: int | None
    content_type: ContentType
    status: MessageStatus
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    page: int
    page_size: int


class StatusResponse(BaseModel):
    connected: bool
    rules_count: int
    rules_active: int
    messages_today: int
    messages_failed_today: int
    last_forward_at: datetime | None
