from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    String,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.intents import MessageIntent
from app.domain.intents.types import IntentLabelSource


class MessageIntentLabel(Base):
    __tablename__ = "message_intent_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    message_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("incoming_messages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    intent: Mapped[MessageIntent] = mapped_column(
        SAEnum(MessageIntent, name="message_intent"),
        nullable=False,
    )

    source: Mapped[IntentLabelSource] = mapped_column(
        SAEnum(IntentLabelSource, name="intent_label_source"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # 간단한 관계 (원하면 IncomingMessage에도 back_populates 추가 가능)
    message = relationship("IncomingMessage", backref="intent_labels")