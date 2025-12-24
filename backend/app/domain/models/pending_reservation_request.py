# backend/app/domain/models/pending_reservation_request.py
"""
Pending Reservation Request 도메인 모델

에어비앤비 예약 요청(Request to Book) 이메일을 저장하고 관리.
호스트가 24시간 내에 수락/거절해야 하는 예약 요청.

설계:
- 기존 IncomingMessage, ReservationInfo 패턴 준수
- DateTime(timezone=True) 사용
- Mapped[Optional[...]] 타입 힌트
"""
from __future__ import annotations

from datetime import datetime, date, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Text,
    Boolean,
    Date,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PendingReservationStatus(str, Enum):
    """예약 요청 상태"""
    pending = "pending"      # 대기 중
    accepted = "accepted"    # 수락됨
    declined = "declined"    # 거절됨
    expired = "expired"      # 만료됨


class PendingReservationRequest(Base):
    """대기 중인 예약 요청"""
    
    __tablename__ = "pending_reservation_requests"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 이메일 식별자
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    
    # Airbnb 식별자
    airbnb_thread_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    reservation_code: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True, index=True)
    listing_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # 숙소 매핑
    property_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    listing_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 게스트 정보
    guest_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    guest_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    guest_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    guest_review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 예약 정보
    checkin_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    checkout_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    nights: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    guest_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    child_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    infant_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pet_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 금액
    expected_payout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nightly_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 처리 URL
    action_url: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 상태
    status: Mapped[str] = mapped_column(
        String(20), 
        default=PendingReservationStatus.pending.value, 
        nullable=False,
        index=True,
    )
    
    # 타임스탬프 (timezone aware)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now, onupdate=datetime.now
    )
    
    def __repr__(self) -> str:
        return (
            f"<PendingReservationRequest("
            f"id={self.id}, "
            f"reservation_code={self.reservation_code}, "
            f"guest_name={self.guest_name}, "
            f"status={self.status}"
            f")>"
        )
