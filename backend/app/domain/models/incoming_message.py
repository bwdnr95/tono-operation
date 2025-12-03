from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, DateTime, Float, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.intents import (
    MessageActor,
    MessageActionability,
    MessageIntent,
)


class IncomingMessage(Base):
    __tablename__ = "incoming_messages"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # Gmail 기본 식별자
    gmail_message_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
    )

    # OTA / 리스팅 메타 정보 (확장용)
    ota: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )
    ota_listing_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    ota_listing_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # 메일 메타 정보
    subject: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    from_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    # 원본 본문
    text_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    html_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ✅ 추출된 “순수 게스트 메시지” (전처리 결과)
    pure_guest_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Origin 분류 결과
    sender_actor: Mapped[MessageActor] = mapped_column(
        SAEnum(MessageActor, name="message_actor"),
        nullable=False,
        default=MessageActor.UNKNOWN,
    )

    actionability: Mapped[MessageActionability] = mapped_column(
        SAEnum(MessageActionability, name="message_actionability"),
        nullable=False,
        default=MessageActionability.UNKNOWN,
    )

    # Intent 분류 결과 (시스템 기준)
    intent: Mapped[MessageIntent | None] = mapped_column(
        SAEnum(MessageIntent, name="message_intent"),
        nullable=True,
    )

    intent_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # TONO 내부 숙소 식별용 코드 (PropertyProfile.property_code 와 연결)
    property_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
