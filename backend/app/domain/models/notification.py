# backend/app/domain/models/notification.py
"""
In-App Notification 도메인 모델

알림 종류:
- safety_alert: 안전 이슈 감지 (block)
- unanswered_warning: 미응답 경고 (30분+)
- oc_reminder: 당일 OC 리마인더
- booking_confirmed: 예약 확정
- booking_cancelled: 예약 취소
- booking_rtb: 예약 요청 (승인 필요)
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationType(str, enum.Enum):
    safety_alert = "safety_alert"
    unanswered_warning = "unanswered_warning"
    oc_reminder = "oc_reminder"
    booking_confirmed = "booking_confirmed"
    booking_cancelled = "booking_cancelled"
    booking_rtb = "booking_rtb"
    new_guest_message = "new_guest_message"
    same_day_checkin = "same_day_checkin"  # 당일 체크인 예약
    overbooking_alert = "overbooking_alert"  # 오버부킹 의심
    complaint_alert = "complaint_alert"  # 🆕 게스트 불만/문제 감지


class NotificationPriority(str, enum.Enum):
    critical = "critical"  # 🔴 즉시 확인 (Safety Alert)
    high = "high"          # 🟠 주의 (예약 취소, 미응답, RTB)
    normal = "normal"      # 🔵 정보 (예약 확정, OC 리마인더)
    low = "low"            # ⚪ 낮음


class NotificationLinkType(str, enum.Enum):
    conversation = "conversation"
    staff_notification = "staff_notification"
    reservation = "reservation"


class Notification(Base):
    __tablename__ = "notifications"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # 알림 내용
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 연결 링크
    link_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    link_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 컨텍스트 정보
    property_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    guest_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    airbnb_thread_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 상태
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Soft delete
    
    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    __table_args__ = (
        Index("idx_notifications_unread", "is_read", "created_at"),
        Index("idx_notifications_type", "type"),
    )
    
    def __repr__(self) -> str:
        return f"<Notification {self.id} type={self.type} priority={self.priority}>"
    
    def mark_as_read(self) -> None:
        self.is_read = True
        self.read_at = datetime.utcnow()
