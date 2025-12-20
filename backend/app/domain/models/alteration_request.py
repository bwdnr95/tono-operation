"""
AlterationRequest: 예약 변경 요청 추적

- 변경 요청 메일 수신 시 생성
- 수락/거절 메일 수신 시 상태 업데이트
- reservation_info 날짜 업데이트에 필요한 requested 날짜 보관
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from enum import Enum

from sqlalchemy import String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlterationStatus(str, Enum):
    """변경 요청 상태"""
    PENDING = "pending"      # 대기 중
    ACCEPTED = "accepted"    # 수락됨
    DECLINED = "declined"    # 거절됨


class AlterationRequest(Base):
    """
    예약 변경 요청 테이블
    
    Flow:
    1. alteration_requested 메일 → pending 상태로 생성
    2. alteration_accepted 메일 → accepted + reservation_info 날짜 업데이트
    3. alteration_declined 메일 → declined
    """
    __tablename__ = "alteration_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # reservation_info 연결
    reservation_info_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("reservation_info.id"), nullable=True, index=True
    )
    
    # 기존 날짜 (매칭용)
    original_checkin: Mapped[date] = mapped_column(Date, nullable=False)
    original_checkout: Mapped[date] = mapped_column(Date, nullable=False)
    
    # 요청된 변경 날짜
    requested_checkin: Mapped[date] = mapped_column(Date, nullable=False)
    requested_checkout: Mapped[date] = mapped_column(Date, nullable=False)
    requested_guest_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 상태
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AlterationStatus.PENDING.value
    )
    
    # Airbnb 식별자
    alteration_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    listing_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    guest_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 원본 메일 정보
    gmail_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AlterationRequest(id={self.id}, "
            f"status={self.status}, "
            f"original={self.original_checkin}~{self.original_checkout}, "
            f"requested={self.requested_checkin}~{self.requested_checkout})>"
        )
