from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Float,
    ForeignKey,
)
from sqlalchemy.sql import func

from app.db.base import Base


class AutoReplyLog(Base):
    __tablename__ = "auto_reply_logs"

    id = Column(Integer, primary_key=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    is_active = Column(Boolean, nullable=False, default=True)

    message_id = Column(
        Integer,
        ForeignKey("incoming_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    property_code = Column(String(32), nullable=True)
    ota = Column(String(32), nullable=True)

    intent = Column(String(64), nullable=False)
    fine_intent = Column(String(128), nullable=True)
    intent_confidence = Column(Float, nullable=True)

    generation_mode = Column(String(64), nullable=True)
    template_id = Column(Integer, nullable=True)
    reply_text = Column(Text, nullable=False)

    send_mode = Column(String(32), nullable=False, default="AUTOPILOT")  # AUTOPILOT / HITL
    sent = Column(Boolean, nullable=False, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    allow_auto_send = Column(Boolean, nullable=False, default=False)

    edited = Column(Boolean, nullable=False, default=False)
    edited_text = Column(Text, nullable=True)
    edited_by = Column(String(64), nullable=True)

    failure_reason = Column(Text, nullable=True)
