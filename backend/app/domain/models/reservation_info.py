"""
ReservationInfo: 예약 확정 시스템 메일에서 파싱한 게스트/예약 정보

- airbnb_thread_id 기준으로 저장
- conversation 생성 전에 미리 저장됨
- LLM context에 포함되어 더 정확한 답변 생성에 활용
"""
from __future__ import annotations

from datetime import datetime, date, time
from typing import Optional
from enum import Enum

from sqlalchemy import (
    String,
    Integer,
    Date,
    Time,
    DateTime,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReservationStatus(str, Enum):
    """예약 상태"""
    # 문의 (예약 전)
    INQUIRY = "inquiry"                      # 예약 전 문의 (BOOKING_INITIAL_INQUIRY)
    
    # 예약 요청 (RTB) 관련
    AWAITING_APPROVAL = "awaiting_approval"  # 호스트 승인 대기 중 (RTB)
    DECLINED = "declined"                    # 호스트 거절
    EXPIRED = "expired"                      # 24시간 초과 만료
    
    # 예약 확정 관련
    CONFIRMED = "confirmed"                  # 예약 확정
    CANCELED = "canceled"                    # 취소됨
    ALTERATION_REQUESTED = "alteration_requested"  # 변경 요청 중
    
    # 수기 입력 (lazy matching 대기)
    PENDING = "pending"                      # 수기 입력, conversation 매칭 대기


class ReservationInfo(Base):
    """
    예약 정보 테이블
    
    - 예약 확정 메일(BOOKING_CONFIRMATION_TO_HOST)에서 파싱
    - 게스트 메시지 메일에서도 파싱 가능 (fallback)
    - airbnb_thread_id로 conversation과 연결
    """
    __tablename__ = "reservation_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # airbnb_thread_id: Gmail thread ID (unique)
    airbnb_thread_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    
    # 예약 상태
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ReservationStatus.CONFIRMED.value
    )
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # RTB 승인 만료 시간
    
    # 게스트 정보
    guest_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    guest_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # RTB 시 게스트 메시지
    guest_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 성인 수
    child_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 어린이 수
    infant_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 유아 수
    pet_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 반려동물 수
    
    # 예약 정보
    reservation_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # HM4WAHCJ2D
    checkin_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    checkout_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    checkin_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    checkout_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    
    # 숙소 정보
    property_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    listing_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    listing_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # 금액 정보
    total_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 게스트 결제 총액
    host_payout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 호스트 수령액
    nights: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 숙박 일수
    
    # 원본 이메일 정보 (디버깅/추적용)
    source_template: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # X-Template 값
    gmail_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 액션 URL (에어비앤비 호스팅 스레드 URL)
    action_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 메타
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<ReservationInfo(airbnb_thread_id={self.airbnb_thread_id}, "
            f"status={self.status}, "
            f"guest={self.guest_name}, "
            f"checkin={self.checkin_date}, checkout={self.checkout_date})>"
        )
    
    def to_llm_context(self) -> str:
        """LLM에게 전달할 컨텍스트 문자열 생성"""
        parts = []
        
        # 예약 상태
        if self.status == ReservationStatus.INQUIRY.value:
            parts.append("💬 예약 상태: 문의 중 (예약 미확정)")
        elif self.status == ReservationStatus.CANCELED.value:
            parts.append("⚠️ 예약 상태: 취소됨")
        elif self.status == ReservationStatus.AWAITING_APPROVAL.value:
            parts.append("⏳ 예약 상태: 승인 대기 중 (예약 요청)")
        elif self.status == ReservationStatus.DECLINED.value:
            parts.append("❌ 예약 상태: 거절됨")
        elif self.status == ReservationStatus.EXPIRED.value:
            parts.append("⏰ 예약 상태: 만료됨")
        
        if self.guest_name:
            parts.append(f"게스트 이름: {self.guest_name}")
        
        if self.checkin_date:
            checkin_str = self.checkin_date.strftime("%Y년 %m월 %d일")
            if self.checkin_time:
                checkin_str += f" {self.checkin_time.strftime('%H:%M')}"
            parts.append(f"체크인: {checkin_str}")
        
        if self.checkout_date:
            checkout_str = self.checkout_date.strftime("%Y년 %m월 %d일")
            if self.checkout_time:
                checkout_str += f" {self.checkout_time.strftime('%H:%M')}"
            parts.append(f"체크아웃: {checkout_str}")
        
        if self.nights:
            parts.append(f"숙박 일수: {self.nights}박")
        
        guest_info = []
        if self.guest_count:
            guest_info.append(f"성인 {self.guest_count}명")
        if self.child_count:
            guest_info.append(f"어린이 {self.child_count}명")
        if self.infant_count:
            guest_info.append(f"유아 {self.infant_count}명")
        if self.pet_count:
            guest_info.append(f"반려동물 {self.pet_count}마리")
        if guest_info:
            parts.append(f"인원: {', '.join(guest_info)}")
        
        if self.reservation_code:
            parts.append(f"예약 코드: {self.reservation_code}")
        
        if self.listing_name:
            parts.append(f"숙소: {self.listing_name}")
        
        return "\n".join(parts) if parts else ""
