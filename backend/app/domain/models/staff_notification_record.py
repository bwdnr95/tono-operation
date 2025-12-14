from __future__ import annotations

from sqlalchemy import (
    Column, Integer, DateTime, Boolean, String,
    Text, JSON, ForeignKey
)
from sqlalchemy.sql import func
from app.db.base import Base


class StaffNotificationRecord(Base):
    __tablename__ = "staff_notifications"

    id = Column(Integer, primary_key=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        nullable=False, onupdate=func.now())

    is_active = Column(Boolean, nullable=False, default=True)

    message_id = Column(Integer, ForeignKey("incoming_messages.id", ondelete="CASCADE"), nullable=False)

    property_code = Column(String(32))
    ota = Column(String(32))
    guest_name = Column(String(128))
    checkin_date = Column(String(32))  # 문자열로 저장 (DATE로 바꿔도 됨)
    checkout_date = Column(String(32))  # 문자열로 저장 (DATE로 바꿔도 됨)

    message_summary = Column(Text, nullable=False)
    follow_up_actions = Column(JSON, nullable=False)

    status = Column(String(32), nullable=False, default="OPEN")
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(String(64))
