import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MessageStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class SyncStatus(str, enum.Enum):
    IDLE = "idle"
    SYNCING = "syncing"
    DONE = "done"


class ContentType(str, enum.Enum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    VOICE = "voice"
    STICKER = "sticker"
    ANIMATION = "animation"
    ALBUM = "album"
    OTHER = "other"


class ForwardRule(Base):
    __tablename__ = "forward_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    filters: Mapped[str | None] = mapped_column(Text)
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus), default=SyncStatus.IDLE
    )
    synced_msg_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["MessageLog"]] = relationship(back_populates="rule")

    __table_args__ = (Index("ix_forward_rules_source", "source_chat_id"),)


class MessageLog(Base):
    __tablename__ = "message_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("forward_rules.id"))
    source_msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType))
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus), default=MessageStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text)
    text_preview: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    rule: Mapped[ForwardRule] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_message_logs_source_msg", "source_msg_id"),
        Index("ix_message_logs_created", "created_at"),
    )
