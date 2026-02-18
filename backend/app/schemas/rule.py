from datetime import datetime

from pydantic import BaseModel


class RuleCreate(BaseModel):
    source_chat_id: int
    target_chat_id: int
    filters: dict | None = None


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    filters: dict | None = None


class RuleResponse(BaseModel):
    id: int
    source_chat_id: int
    target_chat_id: int
    enabled: bool
    filters: dict | None
    sync_status: str
    synced_msg_count: int
    created_at: datetime
    message_count: int

    model_config = {"from_attributes": True}
