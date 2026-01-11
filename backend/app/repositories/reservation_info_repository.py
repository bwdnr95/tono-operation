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

from sqlalchemy import select, or_
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
        status: Optional[str] = None,
        guest_name: Optional[str] = None,
        guest_message: Optional[str] = None,
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
        group_code: Optional[str] = None,
        listing_id: Optional[str] = None,
        listing_name: Optional[str] = None,
        total_price: Optional[int] = None,
        host_payout: Optional[int] = None,
        nights: Optional[int] = None,
        source_template: Optional[str] = None,
        gmail_message_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        action_url: Optional[str] = None,
    ) -> ReservationInfo:
        """새 예약 정보 생성"""
        info = ReservationInfo(
            airbnb_thread_id=airbnb_thread_id,
            guest_name=guest_name,
            guest_message=guest_message,
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
            group_code=group_code,
            listing_id=listing_id,
            listing_name=listing_name,
            total_price=total_price,
            host_payout=host_payout,
            nights=nights,
            source_template=source_template,
            gmail_message_id=gmail_message_id,
            expires_at=expires_at,
            action_url=action_url,
        )
        if status:
            info.status = status
        self.db.add(info)
        self.db.flush()
        
        # 오버부킹 체크 (canceled 제외, 생성 후 체크)
        if status != "canceled":
            self.check_and_notify_overbooking(
                property_code=property_code,
                checkin_date=checkin_date,
                exclude_airbnb_thread_id=None,  # 이미 포함되어 있으므로 제외 불필요
            )
        
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
            updated = self.update(
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
            
            # UPDATE 후 오버부킹 체크 (canceled 제외)
            if updated.status != "canceled":
                self.check_and_notify_overbooking(
                    property_code=updated.property_code,
                    checkin_date=updated.checkin_date,
                    exclude_airbnb_thread_id=None,
                )
            
            return updated
        else:
            # 없으면 새로 생성 (create에서 오버부킹 체크 포함)
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
        property_code: Optional[str],
        guest_name: Optional[str],
        airbnb_thread_id: str,
        checkin_date: Optional[date] = None,
        group_code: Optional[str] = None,
    ) -> Optional[ReservationInfo]:
        """
        pending 상태이거나 airbnb_thread_id가 MANUAL_/pending_으로 시작하는 예약을
        lazy matching으로 찾아서 실제 airbnb_thread_id로 업데이트
        
        매칭 대상:
        - status == "pending" (CSV 수기 입력)
        - airbnb_thread_id가 "MANUAL_" 또는 "pending_"으로 시작
        
        매칭 순서:
        1. property_code + guest_name (부분일치)
        2. property_code + checkin_date (호스트/공동호스트 메시지용)
        3. property_code만 (단일 pending만 있을 때)
        
        group_code만 있는 경우:
        - group_code에 속한 property_code들(LIKE 'group_code%')로 확장하여 매칭
        - 수기 입력된 예약은 이미 숙소 배정이 되어있어 property_code가 있음
        
        Returns:
            업데이트된 ReservationInfo, 없으면 None
            
        Note:
            2차/3차 매칭에서 2건 이상 발견 시 오버부킹 의심 → 알림 발송, 매칭 스킵
        """
        info = None
        
        # property_code도 group_code도 없으면 매칭 불가
        if not property_code and not group_code:
            return None
        
        # 매칭 조건: status가 pending이거나, airbnb_thread_id가 MANUAL_/pending_으로 시작
        pending_condition = or_(
            ReservationInfo.status == "pending",
            ReservationInfo.airbnb_thread_id.like("MANUAL_%"),
            ReservationInfo.airbnb_thread_id.like("pending_%"),
        )
        
        # property_code 조건 설정
        # - property_code가 있으면 정확히 일치
        # - group_code만 있으면 그룹에 속한 모든 property_code (LIKE 'group_code%')
        if property_code:
            property_condition = ReservationInfo.property_code == property_code
        else:
            # group_code만 있는 경우: 해당 그룹의 property_code들로 매칭
            # 예: group_code="2NH" → property_code LIKE "2NH%"
            property_condition = ReservationInfo.property_code.like(f"{group_code}%")
        
        # 1차: guest_name 부분일치 포함
        if guest_name:
            # guest_name 정규화 (공백 제거, 대소문자 무시)
            normalized_name = guest_name.strip()
            stmt = select(ReservationInfo).where(
                pending_condition,
                property_condition,
                ReservationInfo.guest_name.ilike(f"%{normalized_name}%"),
            )
            results = list(self.db.execute(stmt).scalars().all())
            
            if len(results) == 1:
                info = results[0]
            elif len(results) > 1:
                # 동일 이름으로 여러 건 → checkin_date로 추가 필터
                if checkin_date:
                    for r in results:
                        if r.checkin_date == checkin_date:
                            info = r
                            break
                # 그래도 못 찾으면 None (모호함)
        
        # 2차: checkin_date 매칭 (호스트/공동호스트 메시지용)
        if not info and checkin_date:
            stmt = select(ReservationInfo).where(
                pending_condition,
                property_condition,
                ReservationInfo.checkin_date == checkin_date,
            )
            results = list(self.db.execute(stmt).scalars().all())
            
            if len(results) == 1:
                info = results[0]
            elif len(results) > 1:
                # 🚨 오버부킹 의심 → 알림 발송, 매칭 스킵
                # group_code로 매칭한 경우 첫 번째 property_code 사용
                first_property = results[0].property_code if results else (property_code or group_code)
                self._notify_overbooking(
                    property_code=first_property,
                    checkin_date=checkin_date,
                    reservations=results,
                )
                return None
        
        # 3차 fallback: guest_name, checkin_date 없이 (단일 pending만 있을 때)
        if not info:
            stmt = select(ReservationInfo).where(
                pending_condition,
                property_condition,
            )
            results = list(self.db.execute(stmt).scalars().all())
            if len(results) == 1:
                # 단일 pending만 있을 때만 매칭 (모호함 방지)
                info = results[0]
        
        if not info:
            return None
        
        info.airbnb_thread_id = airbnb_thread_id
        info.status = "confirmed"
        info.updated_at = datetime.utcnow()
        self.db.flush()
        return info
    
    def _notify_overbooking(
        self,
        property_code: str,
        checkin_date: date,
        reservations: list[ReservationInfo],
    ) -> None:
        """오버부킹 의심 알림 발송"""
        try:
            from app.services.notification_service import NotificationService
            notification_svc = NotificationService(self.db)
            notification_svc.create_overbooking_alert(
                property_code=property_code,
                checkin_date=str(checkin_date),
                reservation_count=len(reservations),
                guest_names=[r.guest_name or "Unknown" for r in reservations],
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to create overbooking alert: {e}")

    def check_and_notify_overbooking(
        self,
        property_code: Optional[str],
        checkin_date: Optional[date],
        exclude_airbnb_thread_id: Optional[str] = None,
    ) -> bool:
        """
        오버부킹 여부 체크 및 알림 발송
        
        같은 property_code + checkin_date에 2건 이상의 예약이 있으면 오버부킹 의심.
        
        제외 대상 status:
        - canceled: 취소됨
        - declined: 호스트 거절
        - expired: 만료됨
        - inquiry: 문의만 (예약 아님)
        
        Args:
            property_code: 숙소 코드
            checkin_date: 체크인 날짜
            exclude_airbnb_thread_id: 제외할 airbnb_thread_id (자기 자신)
            
        Returns:
            True if overbooking detected, False otherwise
        """
        if not property_code or not checkin_date:
            return False
        
        # 오버부킹 체크 제외 status
        excluded_statuses = ["canceled", "declined", "expired", "inquiry"]
        
        stmt = select(ReservationInfo).where(
            ReservationInfo.property_code == property_code,
            ReservationInfo.checkin_date == checkin_date,
            ReservationInfo.status.notin_(excluded_statuses),
        )
        
        results = list(self.db.execute(stmt).scalars().all())
        
        # 자기 자신 제외
        if exclude_airbnb_thread_id:
            results = [r for r in results if r.airbnb_thread_id != exclude_airbnb_thread_id]
        
        if len(results) >= 2:
            # 오버부킹 의심 → 알림 발송
            self._notify_overbooking(
                property_code=property_code,
                checkin_date=checkin_date,
                reservations=results,
            )
            return True
        
        return False

    def check_date_availability(
        self,
        property_code: str,
        checkin_date: date,
        checkout_date: Optional[date] = None,
        exclude_airbnb_thread_id: Optional[str] = None,
    ) -> dict:
        """
        특정 날짜에 예약 가능 여부 확인 (INQUIRY 문의 시 UI 표시용)
        
        체크인~체크아웃 기간 동안 겹치는 예약이 있는지 확인.
        
        Args:
            property_code: 숙소 코드
            checkin_date: 체크인 날짜
            checkout_date: 체크아웃 날짜 (없으면 checkin_date + 1일)
            exclude_airbnb_thread_id: 제외할 airbnb_thread_id (자기 자신)
            
        Returns:
            {
                "available": bool,
                "conflicts": [
                    {
                        "guest_name": str,
                        "checkin_date": str,
                        "checkout_date": str,
                        "status": str,
                        "reservation_code": str | None,
                    },
                    ...
                ]
            }
        """
        from datetime import timedelta
        
        if not checkout_date:
            checkout_date = checkin_date + timedelta(days=1)
        
        # 유효한 예약 status (충돌 체크 대상)
        # inquiry는 제외 (문의는 예약이 아님)
        valid_statuses = ["confirmed", "pending", "awaiting_approval", "alteration_requested"]
        
        # 날짜 겹침 조건:
        # 기존 예약의 checkin < 새 checkout AND 기존 예약의 checkout > 새 checkin
        stmt = select(ReservationInfo).where(
            ReservationInfo.property_code == property_code,
            ReservationInfo.status.in_(valid_statuses),
            ReservationInfo.checkin_date < checkout_date,
            ReservationInfo.checkout_date > checkin_date,
        )
        
        results = list(self.db.execute(stmt).scalars().all())
        
        # 자기 자신 제외
        if exclude_airbnb_thread_id:
            results = [r for r in results if r.airbnb_thread_id != exclude_airbnb_thread_id]
        
        conflicts = []
        for r in results:
            conflicts.append({
                "guest_name": r.guest_name or "Unknown",
                "checkin_date": str(r.checkin_date) if r.checkin_date else None,
                "checkout_date": str(r.checkout_date) if r.checkout_date else None,
                "status": r.status,
                "reservation_code": r.reservation_code,
            })
        
        return {
            "available": len(conflicts) == 0,
            "conflicts": conflicts,
        }


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
