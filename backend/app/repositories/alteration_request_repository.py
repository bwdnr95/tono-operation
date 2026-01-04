"""
AlterationRequest Repository

예약 변경 요청 저장/조회/업데이트
- 변경 요청 메일 수신 시 pending 상태로 저장
- 변경 수락/거절 시 상태 업데이트
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.alteration_request import AlterationRequest, AlterationStatus


class AlterationRequestRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        reservation_info_id: Optional[int] = None,
        original_checkin: date,
        original_checkout: date,
        requested_checkin: date,
        requested_checkout: date,
        requested_guest_count: Optional[int] = None,
        alteration_id: Optional[str] = None,
        listing_name: Optional[str] = None,
        guest_name: Optional[str] = None,
        gmail_message_id: Optional[str] = None,
    ) -> AlterationRequest:
        """
        새 변경 요청 생성 (pending 상태)
        """
        request = AlterationRequest(
            reservation_info_id=reservation_info_id,
            original_checkin=original_checkin,
            original_checkout=original_checkout,
            requested_checkin=requested_checkin,
            requested_checkout=requested_checkout,
            requested_guest_count=requested_guest_count,
            status=AlterationStatus.PENDING.value,
            alteration_id=alteration_id,
            listing_name=listing_name,
            guest_name=guest_name,
            gmail_message_id=gmail_message_id,
        )
        self.db.add(request)
        self.db.flush()
        return request

    def exists_by_gmail_message_id(self, gmail_message_id: str) -> bool:
        """
        gmail_message_id로 이미 처리된 변경 요청이 있는지 확인 (중복 방지)
        """
        stmt = (
            select(AlterationRequest.id)
            .where(AlterationRequest.gmail_message_id == gmail_message_id)
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None

    def get_pending_by_reservation_info_id(
        self,
        reservation_info_id: int,
    ) -> Optional[AlterationRequest]:
        """
        reservation_info_id로 pending 상태인 변경 요청 조회
        
        Returns:
            가장 최근 pending 요청, 없으면 None
        """
        stmt = (
            select(AlterationRequest)
            .where(
                AlterationRequest.reservation_info_id == reservation_info_id,
                AlterationRequest.status == AlterationStatus.PENDING.value,
            )
            .order_by(AlterationRequest.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_pending_by_original_dates(
        self,
        original_checkin: date,
        original_checkout: date,
        listing_name: Optional[str] = None,
    ) -> Optional[AlterationRequest]:
        """
        기존 날짜로 pending 상태인 변경 요청 조회
        
        매칭 실패 시 fallback으로 사용
        """
        stmt = (
            select(AlterationRequest)
            .where(
                AlterationRequest.original_checkin == original_checkin,
                AlterationRequest.original_checkout == original_checkout,
                AlterationRequest.status == AlterationStatus.PENDING.value,
            )
            .order_by(AlterationRequest.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def accept(
        self,
        alteration_request: AlterationRequest,
    ) -> AlterationRequest:
        """
        변경 요청 수락 처리
        """
        alteration_request.status = AlterationStatus.ACCEPTED.value
        alteration_request.resolved_at = datetime.utcnow()
        self.db.flush()
        return alteration_request

    def decline(
        self,
        alteration_request: AlterationRequest,
    ) -> AlterationRequest:
        """
        변경 요청 거절 처리
        """
        alteration_request.status = AlterationStatus.DECLINED.value
        alteration_request.resolved_at = datetime.utcnow()
        self.db.flush()
        return alteration_request

    def get_all_pending(self) -> List[AlterationRequest]:
        """
        모든 pending 상태 변경 요청 조회 (디버깅/관리용)
        """
        stmt = (
            select(AlterationRequest)
            .where(AlterationRequest.status == AlterationStatus.PENDING.value)
            .order_by(AlterationRequest.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())
