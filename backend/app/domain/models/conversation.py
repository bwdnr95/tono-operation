from __future__ import annotations

from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _enum_values(enum_cls):
    # SQLAlchemy가 Enum "이름"이 아니라 Enum.value (예: 'pass')로 저장/로드하도록 강제
    return [e.value for e in enum_cls]


class ConversationChannel(str, Enum):
    gmail = "gmail"


class ConversationStatus(str, Enum):
    open = "open"
    needs_review = "needs_review"
    ready_to_send = "ready_to_send"
    sent = "sent"
    blocked = "blocked"


class SafetyStatus(str, Enum):
    pass_ = "pass"
    review = "review"
    block = "block"


class SendAction(str, Enum):
    preview = "preview"
    send = "send"
    bulk_send = "bulk_send"


class BulkSendJobStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    partial_failed = "partial_failed"
    failed = "failed"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    channel: Mapped[ConversationChannel] = mapped_column(
        SAEnum(
            ConversationChannel,
            name="conversation_channel",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ConversationChannel.gmail,
        index=True,
    )

    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(
            ConversationStatus,
            name="conversation_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ConversationStatus.open,
        index=True,
    )

    safety_status: Mapped[SafetyStatus] = mapped_column(
        SAEnum(
            SafetyStatus,
            name="conversation_safety_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SafetyStatus.pass_,
        index=True,
    )

    last_message_id: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    draft_replies: Mapped[list["DraftReply"]] = relationship(
        "DraftReply",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="DraftReply.created_at",
    )

    __table_args__ = (
        Index("ux_conversations_channel_thread", "channel", "thread_id", unique=True),
    )


class DraftReply(Base):
    __tablename__ = "draft_replies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )

    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    safety_status: Mapped[SafetyStatus] = mapped_column(
        SAEnum(
            SafetyStatus,
            name="draft_reply_safety_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SafetyStatus.pass_,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="draft_replies")


class SendActionLog(Base):
    __tablename__ = "send_action_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    message_id: Mapped[int | None] = mapped_column(nullable=True)

    action: Mapped[SendAction] = mapped_column(
        SAEnum(
            SendAction,
            name="send_action",
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class BulkSendJob(Base):
    __tablename__ = "bulk_send_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    conversation_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)

    status: Mapped[BulkSendJobStatus] = mapped_column(
        SAEnum(
            BulkSendJobStatus,
            name="bulk_send_job_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=BulkSendJobStatus.pending,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
