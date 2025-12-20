"""
ReservationInfo Repository

예약 정보 저장/조회/업데이트
- 시스템 메일(예약 확정)에서 파싱한 정보 저장
- 게스트 메시지에서 파싱한 정보로 fallback 저장
- conversation 생성 시 조회해서 연결
"""
from __future__ import annotations

from datetime import datetime, date, time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.domain.models.reservation_info import ReservationInfo, ReservationStatus


class ReservationInfoRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_airbnb_thread_id(self, airbnb_thread_id: str) -> Optional[ReservationInfo]:
        """airbnb_thread_id로 예약 정보 조회"""
        stmt = select(ReservationInfo).where(ReservationInfo.airbnb_thread_id == airbnb_thread_id)
        return self.db.execute(stmt).scalar_one_or_none()
    
    def get_by_reservation_code(self, reservation_code: str) -> Optional[ReservationInfo]:
        """reservation_code로 예약 정보 조회"""
        stmt = select(ReservationInfo).where(ReservationInfo.reservation_code == reservation_code)
        return self.db.execute(stmt).scalar_one_or_none()
    
    def exists(self, airbnb_thread_id: str) -> bool:
        """airbnb_thread_id로 예약 정보 존재 여부 확인"""
        return self.get_by_airbnb_thread_id(airbnb_thread_id) is not None

    def create(
        self,
        airbnb_thread_id: str,
        *,
        guest_name: Optional[str] = None,
        guest_count: Optional[int] = None,
        child_count: Optional[int] = None,
        infant_count: Optional[int] = None,
        pet_count: Optional[int] = None,
        reservation_code: Optional[str] = None,
        checkin_date: Optional[date] = None,
        checkout_date: Optional[date] = None,
        checkin_time: Optional[time] = None,
        checkout_time: Optional[time] = None,
        property_code: Optional[str] = None,
        listing_id: Optional[str] = None,
        listing_name: Optional[str] = None,
        total_price: Optional[int] = None,
        host_payout: Optional[int] = None,
        nights: Optional[int] = None,
        source_template: Optional[str] = None,
        gmail_message_id: Optional[str] = None,
    ) -> ReservationInfo:
        """새 예약 정보 생성"""
        info = ReservationInfo(
            airbnb_thread_id=airbnb_thread_id,
            guest_name=guest_name,
            guest_count=guest_count,
            child_count=child_count,
            infant_count=infant_count,
            pet_count=pet_count,
            reservation_code=reservation_code,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            checkin_time=checkin_time,
            checkout_time=checkout_time,
            property_code=property_code,
            listing_id=listing_id,
            listing_name=listing_name,
            total_price=total_price,
            host_payout=host_payout,
            nights=nights,
            source_template=source_template,
            gmail_message_id=gmail_message_id,
        )
        self.db.add(info)
        self.db.flush()
        return info

    def update(
        self,
        info: ReservationInfo,
        **kwargs,
    ) -> ReservationInfo:
        """기존 예약 정보 업데이트 (None이 아닌 값만)"""
        for key, value in kwargs.items():
            if value is not None and hasattr(info, key):
                setattr(info, key, value)
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info

    def upsert(
        self,
        airbnb_thread_id: str,
        *,
        guest_name: Optional[str] = None,
        guest_count: Optional[int] = None,
        child_count: Optional[int] = None,
        infant_count: Optional[int] = None,
        pet_count: Optional[int] = None,
        reservation_code: Optional[str] = None,
        checkin_date: Optional[date] = None,
        checkout_date: Optional[date] = None,
        checkin_time: Optional[time] = None,
        checkout_time: Optional[time] = None,
        property_code: Optional[str] = None,
        listing_id: Optional[str] = None,
        listing_name: Optional[str] = None,
        total_price: Optional[int] = None,
        host_payout: Optional[int] = None,
        nights: Optional[int] = None,
        source_template: Optional[str] = None,
        gmail_message_id: Optional[str] = None,
    ) -> ReservationInfo:
        """
        예약 정보 upsert (있으면 UPDATE, 없으면 INSERT)
        
        UPDATE 시: None이 아닌 값만 업데이트 (기존 값 유지)
        """
        existing = self.get_by_airbnb_thread_id(airbnb_thread_id)
        
        if existing:
            # 기존 값이 있으면 None이 아닌 값만 업데이트
            return self.update(
                existing,
                guest_name=guest_name,
                guest_count=guest_count,
                child_count=child_count,
                infant_count=infant_count,
                pet_count=pet_count,
                reservation_code=reservation_code,
                checkin_date=checkin_date,
                checkout_date=checkout_date,
                checkin_time=checkin_time,
                checkout_time=checkout_time,
                property_code=property_code,
                listing_id=listing_id,
                listing_name=listing_name,
                total_price=total_price,
                host_payout=host_payout,
                nights=nights,
                source_template=source_template,
                gmail_message_id=gmail_message_id,
            )
        else:
            # 없으면 새로 생성
            return self.create(
                airbnb_thread_id=airbnb_thread_id,
                guest_name=guest_name,
                guest_count=guest_count,
                child_count=child_count,
                infant_count=infant_count,
                pet_count=pet_count,
                reservation_code=reservation_code,
                checkin_date=checkin_date,
                checkout_date=checkout_date,
                checkin_time=checkin_time,
                checkout_time=checkout_time,
                property_code=property_code,
                listing_id=listing_id,
                listing_name=listing_name,
                total_price=total_price,
                host_payout=host_payout,
                nights=nights,
                source_template=source_template,
                gmail_message_id=gmail_message_id,
            )

    def cancel_by_reservation_code(self, reservation_code: str) -> Optional[ReservationInfo]:
        """
        예약 코드로 찾아서 취소 상태로 변경
        
        Returns:
            취소된 ReservationInfo, 없으면 None
        """
        info = self.get_by_reservation_code(reservation_code)
        if not info:
            return None
        
        info.status = ReservationStatus.CANCELED.value
        info.canceled_at = datetime.utcnow()
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info
    
    def cancel_by_airbnb_thread_id(self, airbnb_thread_id: str) -> Optional[ReservationInfo]:
        """
        airbnb_thread_id로 찾아서 취소 상태로 변경
        
        Returns:
            취소된 ReservationInfo, 없으면 None
        """
        info = self.get_by_airbnb_thread_id(airbnb_thread_id)
        if not info:
            return None
        
        info.status = ReservationStatus.CANCELED.value
        info.canceled_at = datetime.utcnow()
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info
    
    def update_dates_by_reservation_code(
        self,
        reservation_code: str,
        checkin_date: Optional[date] = None,
        checkout_date: Optional[date] = None,
    ) -> Optional[ReservationInfo]:
        """
        예약 코드로 찾아서 날짜 업데이트 (변경 완료 시)
        
        Returns:
            업데이트된 ReservationInfo, 없으면 None
        """
        info = self.get_by_reservation_code(reservation_code)
        if not info:
            return None
        
        if checkin_date:
            info.checkin_date = checkin_date
        if checkout_date:
            info.checkout_date = checkout_date
        
        # nights 재계산
        if info.checkin_date and info.checkout_date:
            info.nights = (info.checkout_date - info.checkin_date).days
        
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info

    def find_by_listing_and_dates(
        self,
        listing_name: str,
        checkin_date: date,
        checkout_date: date,
    ) -> Optional[ReservationInfo]:
        """
        숙소명 + 체크인/체크아웃 날짜로 예약 정보 조회
        
        주로 alteration_request 매칭에 사용 (변경 요청 메일에는 reservation_code가 없음)
        
        Args:
            listing_name: 숙소명 (부분 일치)
            checkin_date: 체크인 날짜
            checkout_date: 체크아웃 날짜
            
        Returns:
            매칭되는 ReservationInfo, 없으면 None
        """
        # 정확한 날짜 매칭 + 숙소명 부분 일치
        stmt = select(ReservationInfo).where(
            ReservationInfo.checkin_date == checkin_date,
            ReservationInfo.checkout_date == checkout_date,
            ReservationInfo.listing_name.ilike(f"%{listing_name[:50]}%"),  # 앞 50자만 비교
            ReservationInfo.status != ReservationStatus.CANCELED.value,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_airbnb_thread_id_by_reservation_code(
        self,
        reservation_code: str,
        airbnb_thread_id: str,
    ) -> Optional[ReservationInfo]:
        """
        reservation_code로 찾아서 airbnb_thread_id 업데이트 (lazy matching)
        
        placeholder airbnb_thread_id가 있는 경우:
        - csv_import_xxx (CSV import로 생성)
        - pending_xxx (booking_confirmation 메일로 생성)
        
        게스트 메시지 수신 시 실제 airbnb_thread_id로 업데이트.
        
        Returns:
            업데이트된 ReservationInfo, 없으면 None
        """
        info = self.get_by_reservation_code(reservation_code)
        if not info:
            return None
        
        # placeholder airbnb_thread_id면 무조건 업데이트
        is_placeholder = info.airbnb_thread_id and (
            info.airbnb_thread_id.startswith("csv_import_") or 
            info.airbnb_thread_id.startswith("pending_")
        )
        
        # 이미 실제 airbnb_thread_id가 있고 같지 않으면 스킵
        if info.airbnb_thread_id and not is_placeholder and info.airbnb_thread_id != airbnb_thread_id:
            return info
        
        info.airbnb_thread_id = airbnb_thread_id
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info

    def set_status(
        self,
        reservation_info_id: int,
        status: str,
    ) -> Optional[ReservationInfo]:
        """
        ID로 찾아서 상태 변경
        
        Returns:
            업데이트된 ReservationInfo, 없으면 None
        """
        stmt = select(ReservationInfo).where(ReservationInfo.id == reservation_info_id)
        info = self.db.execute(stmt).scalar_one_or_none()
        if not info:
            return None
        
        info.status = status
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info

    def update_pending_reservation_by_lazy_match(
        self,
        checkin_date: date,
        property_code: str,
        guest_name: Optional[str],
        airbnb_thread_id: str,
    ) -> Optional[ReservationInfo]:
        """
        pending 상태의 예약을 lazy matching으로 찾아서
        airbnb_thread_id 업데이트 + status를 confirmed로 변경
        
        매칭 순서:
        1. checkin_date + property_code + guest_name (부분일치)
        2. checkin_date + property_code (fallback)
        
        Returns:
            업데이트된 ReservationInfo, 없으면 None
        """
        info = None
        
        # 1차: guest_name 부분일치 포함
        if guest_name:
            stmt = select(ReservationInfo).where(
                ReservationInfo.status == "pending",
                ReservationInfo.checkin_date == checkin_date,
                ReservationInfo.property_code == property_code,
                ReservationInfo.guest_name.ilike(f"%{guest_name}%"),
            )
            info = self.db.execute(stmt).scalar_one_or_none()
        
        # 2차 fallback: guest_name 없이
        if not info:
            stmt = select(ReservationInfo).where(
                ReservationInfo.status == "pending",
                ReservationInfo.checkin_date == checkin_date,
                ReservationInfo.property_code == property_code,
            )
            info = self.db.execute(stmt).scalar_one_or_none()
        
        if not info:
            return None
        
        info.airbnb_thread_id = airbnb_thread_id
        info.status = "confirmed"
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info


def _parse_time_string(time_str: Optional[str]) -> Optional[time]:
    """
    "16:00" 형식의 문자열을 time 객체로 변환
    """
    if not time_str:
        return None
    try:
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None
