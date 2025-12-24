# backend/app/repositories/pending_reservation_request_repository.py
"""
Pending Reservation Request Repository

예약 요청 데이터 접근 레이어.

설계:
- 기존 ReservationInfoRepository 패턴 준수
- select().where() 스타일
- 타임존 비교는 func.now() 사용
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.domain.models.pending_reservation_request import (
    PendingReservationRequest,
    PendingReservationStatus,
)


class PendingReservationRequestRepository:
    """대기 중 예약 요청 Repository"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # =========================================================================
    # 조회
    # =========================================================================
    
    def get_by_id(self, request_id: int) -> Optional[PendingReservationRequest]:
        """ID로 조회"""
        stmt = select(PendingReservationRequest).where(
            PendingReservationRequest.id == request_id
        )
        return self.db.execute(stmt).scalar_one_or_none()
    
    def get_by_gmail_message_id(
        self,
        gmail_message_id: str,
    ) -> Optional[PendingReservationRequest]:
        """Gmail 메시지 ID로 조회"""
        stmt = select(PendingReservationRequest).where(
            PendingReservationRequest.gmail_message_id == gmail_message_id
        )
        return self.db.execute(stmt).scalar_one_or_none()
    
    def get_by_reservation_code(
        self,
        reservation_code: str,
    ) -> Optional[PendingReservationRequest]:
        """예약 코드로 조회"""
        stmt = select(PendingReservationRequest).where(
            PendingReservationRequest.reservation_code == reservation_code
        )
        return self.db.execute(stmt).scalar_one_or_none()
    
    def exists_by_gmail_message_id(self, gmail_message_id: str) -> bool:
        """Gmail 메시지 ID로 존재 여부 확인"""
        return self.get_by_gmail_message_id(gmail_message_id) is not None
    
    # =========================================================================
    # 목록 조회
    # =========================================================================
    
    def get_pending_list(
        self,
        property_code: Optional[str] = None,
        include_expired: bool = False,
        limit: int = 50,
    ) -> List[PendingReservationRequest]:
        """
        대기 중인 예약 요청 목록 조회.
        
        Args:
            property_code: 특정 숙소만 필터링 (None이면 전체)
            include_expired: 만료된 요청도 포함할지
            limit: 최대 조회 개수
        
        Returns:
            예약 요청 목록 (expires_at ASC 정렬 - 급한 것 먼저)
        """
        conditions = [
            PendingReservationRequest.status == PendingReservationStatus.pending.value
        ]
        
        if property_code:
            conditions.append(PendingReservationRequest.property_code == property_code)
        
        if not include_expired:
            # func.now() 사용하여 타임존 문제 회피
            conditions.append(
                or_(
                    PendingReservationRequest.expires_at.is_(None),
                    PendingReservationRequest.expires_at > func.now()
                )
            )
        
        stmt = (
            select(PendingReservationRequest)
            .where(and_(*conditions))
            .order_by(PendingReservationRequest.expires_at.asc().nullslast())
            .limit(limit)
        )
        
        return list(self.db.execute(stmt).scalars().all())
    
    def count_pending(
        self,
        property_code: Optional[str] = None,
    ) -> int:
        """
        대기 중인 예약 요청 개수 조회 (만료되지 않은 것만).
        """
        conditions = [
            PendingReservationRequest.status == PendingReservationStatus.pending.value,
            or_(
                PendingReservationRequest.expires_at.is_(None),
                PendingReservationRequest.expires_at > func.now()
            )
        ]
        
        if property_code:
            conditions.append(PendingReservationRequest.property_code == property_code)
        
        stmt = (
            select(func.count(PendingReservationRequest.id))
            .where(and_(*conditions))
        )
        
        return self.db.execute(stmt).scalar() or 0
    
    # =========================================================================
    # 생성
    # =========================================================================
    
    def create(
        self,
        gmail_message_id: str,
        action_url: str,
        *,
        airbnb_thread_id: Optional[str] = None,
        reservation_code: Optional[str] = None,
        listing_id: Optional[str] = None,
        property_code: Optional[str] = None,
        listing_name: Optional[str] = None,
        guest_name: Optional[str] = None,
        guest_message: Optional[str] = None,
        guest_verified: bool = False,
        guest_review_count: Optional[int] = None,
        checkin_date=None,
        checkout_date=None,
        nights: Optional[int] = None,
        guest_count: Optional[int] = None,
        child_count: Optional[int] = None,
        infant_count: Optional[int] = None,
        pet_count: Optional[int] = None,
        expected_payout: Optional[int] = None,
        nightly_rate: Optional[int] = None,
        received_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> PendingReservationRequest:
        """새 예약 요청 생성"""
        request = PendingReservationRequest(
            gmail_message_id=gmail_message_id,
            action_url=action_url,
            airbnb_thread_id=airbnb_thread_id,
            reservation_code=reservation_code,
            listing_id=listing_id,
            property_code=property_code,
            listing_name=listing_name,
            guest_name=guest_name,
            guest_message=guest_message,
            guest_verified=guest_verified,
            guest_review_count=guest_review_count,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            nights=nights,
            guest_count=guest_count,
            child_count=child_count,
            infant_count=infant_count,
            pet_count=pet_count,
            expected_payout=expected_payout,
            nightly_rate=nightly_rate,
            received_at=received_at,
            expires_at=expires_at,
            status=PendingReservationStatus.pending.value,
        )
        
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        
        return request
    
    # =========================================================================
    # 상태 변경
    # =========================================================================
    
    def update_status(
        self,
        request_id: int,
        new_status: str,
    ) -> Optional[PendingReservationRequest]:
        """
        상태 업데이트.
        
        Args:
            request_id: 요청 ID
            new_status: 새 상태 (accepted, declined, expired)
        """
        request = self.get_by_id(request_id)
        if not request:
            return None
        
        request.status = new_status
        request.responded_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(request)
        
        return request
    
    def mark_as_accepted(
        self,
        reservation_code: str,
    ) -> Optional[PendingReservationRequest]:
        """
        예약 확정 메일 수신 시 해당 요청을 accepted로 변경.
        BOOKING_CONFIRMATION 처리 시 호출.
        """
        request = self.get_by_reservation_code(reservation_code)
        if request and request.status == PendingReservationStatus.pending.value:
            request.status = PendingReservationStatus.accepted.value
            request.responded_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(request)
        return request
    
    def expire_old_requests(self) -> int:
        """
        만료된 요청들의 상태를 'expired'로 업데이트.
        
        Returns:
            업데이트된 요청 개수
        """
        stmt = (
            select(PendingReservationRequest)
            .where(
                PendingReservationRequest.status == PendingReservationStatus.pending.value,
                PendingReservationRequest.expires_at.isnot(None),
                PendingReservationRequest.expires_at < func.now(),
            )
        )
        
        requests = list(self.db.execute(stmt).scalars().all())
        count = 0
        
        for req in requests:
            req.status = PendingReservationStatus.expired.value
            count += 1
        
        if count > 0:
            self.db.commit()
        
        return count
