from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    Date,
    Float,
    Boolean,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageDirection(str, Enum):
    incoming = "incoming"
    outgoing = "outgoing"


# MessageActor는 app.domain.intents.message_origin에서 import
from app.domain.intents.message_origin import MessageActor, MessageActionability
from app.domain.intents.types import MessageIntent


class IncomingMessage(Base):
    """
    DB 스키마(incoming_messages)와 ORM 필드가 1:1로 맞아야 한다.
    fine_intent / has_attachment / is_system_generated 등 누락되면
    서비스단(_ensure_intent 등)에서 AttributeError가 난다.
    """

    __tablename__ = "incoming_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    gmail_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)  # Gmail API threadId
    airbnb_thread_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    from_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reply_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Reply-To 헤더

    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pure_guest_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sender_actor: Mapped[Optional[MessageActor]] = mapped_column(
        SQLEnum(MessageActor, native_enum=False, length=32), nullable=True
    )
    actionability: Mapped[Optional[MessageActionability]] = mapped_column(
        SQLEnum(MessageActionability, native_enum=False, length=32), nullable=True
    )

    # ✅ 반드시 존재해야 함 (유저가 올린 컬럼 목록에 있음)
    intent: Mapped[Optional[MessageIntent]] = mapped_column(
        SQLEnum(MessageIntent, native_enum=False, length=32), nullable=True
    )
    intent_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    ota: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ota_listing_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ota_listing_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    property_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # ✅ fine_intent 계열 (유저 컬럼 목록에 있음)
    fine_intent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fine_intent_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fine_intent_reasons: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    suggested_action: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    allow_auto_send: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_auto_reply_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    guest_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    checkin_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    checkout_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ✅ direction/content (유저 컬럼 목록에 있음)
    direction: Mapped[Optional[MessageDirection]] = mapped_column(
        SQLEnum(MessageDirection, native_enum=False, length=16), nullable=True
    )
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ✅ has_attachment / is_system_generated (유저 컬럼 목록에 있음)
    has_attachment: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_system_generated: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now, onupdate=datetime.now
    )
