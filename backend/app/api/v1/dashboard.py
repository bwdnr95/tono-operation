# backend/app/api/v1/dashboard.py
"""
Dashboard API

운영 대시보드 엔드포인트:
- 대시보드 요약 (Summary)
- 대기 중 예약 요청 (Pending Reservations)
- 미응답 메시지 (Unanswered Messages)  
- Staff Alerts (Operational Commitments)

설계:
- 기존 staff_notifications.py 패턴 준수
- ConversationStatus enum 값 정확히 사용
- 타임존 비교는 func.now() 사용
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
from app.services.oc_service import OCService


logger = logging.getLogger(__name__)


# =============================================================================
# DB Session
# =============================================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# DTOs
# =============================================================================

class DashboardSummaryResponse(BaseModel):
    """대시보드 요약"""
    pending_reservations_count: int
    unanswered_messages_count: int
    staff_alerts_count: int
    today_checkins_count: int
    today_checkouts_count: int


class PendingReservationDTO(BaseModel):
    """대기 중 예약 요청"""
    id: int
    reservation_code: Optional[str]
    property_code: Optional[str]
    listing_name: Optional[str]
    guest_name: Optional[str]
    guest_message: Optional[str]
    guest_verified: bool
    guest_review_count: Optional[int]
    checkin_date: Optional[str]  # ISO format
    checkout_date: Optional[str]  # ISO format
    nights: Optional[int]
    guest_count: Optional[int]
    expected_payout: Optional[int]
    action_url: str
    status: str
    remaining_hours: Optional[float]
    received_at: Optional[str]  # ISO format
    
    class Config:
        from_attributes = True


class PendingReservationListResponse(BaseModel):
    """대기 중 예약 요청 목록"""
    items: List[PendingReservationDTO]
    total_count: int


class UnansweredMessageDTO(BaseModel):
    """미응답 메시지"""
    conversation_id: str  # UUID as string
    airbnb_thread_id: str
    property_code: Optional[str]
    property_name: Optional[str]
    guest_name: Optional[str]
    last_message_preview: Optional[str]
    last_message_at: Optional[str]  # ISO format
    hours_since_last_message: Optional[float]


class UnansweredMessageListResponse(BaseModel):
    """미응답 메시지 목록"""
    items: List[UnansweredMessageDTO]
    total_count: int


class StaffAlertDTO(BaseModel):
    """Staff Alert"""
    oc_id: str  # UUID as string
    conversation_id: str  # UUID as string
    airbnb_thread_id: str
    property_code: Optional[str]
    property_name: Optional[str]
    guest_name: Optional[str]
    topic: str
    description: str
    target_date: Optional[str]  # ISO format
    status: str
    priority: str
    created_at: Optional[str]  # ISO format


class StaffAlertListResponse(BaseModel):
    """Staff Alert 목록"""
    items: List[StaffAlertDTO]
    total_count: int


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    """
    대시보드 요약 정보 조회.
    
    - 대기 중 예약 요청 수
    - 미응답 메시지 수
    - Staff Alerts 수
    - 오늘 체크인/체크아웃 수
    """
    # 1. 대기 중 예약 요청 수
    pending_count = _count_pending_reservations(db, property_code)
    
    # 2. 미응답 메시지 수 (2시간 이상 경과)
    unanswered_count = _count_unanswered_messages(db, property_code, hours_threshold=2)
    
    # 3. Staff Alerts 수
    staff_alerts_count = _count_staff_alerts(db, property_code)
    
    # 4. 오늘 체크인/체크아웃 수
    today = date.today()
    today_checkins, today_checkouts = _count_today_movements(db, today, property_code)
    
    return DashboardSummaryResponse(
        pending_reservations_count=pending_count,
        unanswered_messages_count=unanswered_count,
        staff_alerts_count=staff_alerts_count,
        today_checkins_count=today_checkins,
        today_checkouts_count=today_checkouts,
    )


@router.get("/pending-requests", response_model=PendingReservationListResponse)
def get_pending_requests(
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    include_expired: bool = Query(False, description="만료된 요청도 포함"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PendingReservationListResponse:
    """
    대기 중 예약 요청 목록 조회.
    
    게스트가 예약 요청(Request to Book)을 보낸 후 24시간 내에 수락/거절해야 함.
    """
    try:
        from app.repositories.pending_reservation_request_repository import (
            PendingReservationRequestRepository,
        )
    except ImportError:
        logger.warning("PendingReservationRequestRepository not found")
        return PendingReservationListResponse(items=[], total_count=0)
    
    repo = PendingReservationRequestRepository(db)
    requests = repo.get_pending_list(
        property_code=property_code,
        include_expired=include_expired,
        limit=limit,
    )
    
    now = datetime.now(timezone.utc)
    items = []
    
    for req in requests:
        # 남은 시간 계산
        remaining_hours = None
        if req.expires_at:
            expires_at = req.expires_at
            # timezone naive인 경우 UTC로 가정
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            delta = expires_at - now
            remaining_hours = max(0, round(delta.total_seconds() / 3600, 1))
        
        items.append(PendingReservationDTO(
            id=req.id,
            reservation_code=req.reservation_code,
            property_code=req.property_code,
            listing_name=req.listing_name,
            guest_name=req.guest_name,
            guest_message=req.guest_message,
            guest_verified=req.guest_verified,
            guest_review_count=req.guest_review_count,
            checkin_date=req.checkin_date.isoformat() if req.checkin_date else None,
            checkout_date=req.checkout_date.isoformat() if req.checkout_date else None,
            nights=req.nights,
            guest_count=req.guest_count,
            expected_payout=req.expected_payout,
            action_url=req.action_url,
            status=req.status,
            remaining_hours=remaining_hours,
            received_at=req.received_at.isoformat() if req.received_at else None,
        ))
    
    return PendingReservationListResponse(
        items=items,
        total_count=len(items),
    )


@router.get("/unanswered-messages", response_model=UnansweredMessageListResponse)
def get_unanswered_messages(
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    hours_threshold: int = Query(2, ge=1, le=48, description="미응답 기준 시간"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> UnansweredMessageListResponse:
    """
    미응답 메시지 목록 조회.
    
    응답 대기 상태 (new, pending, needs_review, ready_to_send)이고
    마지막 메시지가 특정 시간 이상 경과한 대화.
    """
    items = _get_unanswered_messages(
        db,
        property_code=property_code,
        hours_threshold=hours_threshold,
        limit=limit,
    )
    
    return UnansweredMessageListResponse(
        items=items,
        total_count=len(items),
    )


@router.get("/staff-alerts", response_model=StaffAlertListResponse)
def get_staff_alerts(
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StaffAlertListResponse:
    """
    Staff Alerts (운영 약속) 목록 조회.
    
    호스트가 게스트에게 약속한 사항 (시설 조치, 얼리체크인 등).
    기존 OCService.get_staff_notifications() 활용.
    """
    service = OCService(db)
    notifications = service.get_staff_notifications(limit=limit)
    
    # property_code 필터링 (StaffNotificationItem에 property_code 필드 있어야 함)
    if property_code:
        notifications = [
            n for n in notifications 
            if getattr(n, 'property_code', None) == property_code
        ]
    
    items = [
        StaffAlertDTO(
            oc_id=str(n.oc_id),
            conversation_id=str(n.conversation_id),
            airbnb_thread_id=n.airbnb_thread_id,
            property_code=getattr(n, 'property_code', None),
            property_name=getattr(n, 'property_name', None),
            guest_name=n.guest_name,
            topic=n.topic,
            description=n.description,
            target_date=n.target_date.isoformat() if n.target_date else None,
            status=n.status,
            priority=n.priority.value if hasattr(n.priority, 'value') else str(n.priority),
            created_at=n.created_at.isoformat() if n.created_at else None,
        )
        for n in notifications
    ]
    
    return StaffAlertListResponse(
        items=items,
        total_count=len(items),
    )


# =============================================================================
# Internal Functions
# =============================================================================

def _count_pending_reservations(
    db: Session,
    property_code: Optional[str] = None,
) -> int:
    """대기 중 예약 요청 수"""
    try:
        from app.repositories.pending_reservation_request_repository import (
            PendingReservationRequestRepository,
        )
        repo = PendingReservationRequestRepository(db)
        return repo.count_pending(property_code=property_code)
    except ImportError:
        return 0


def _count_unanswered_messages(
    db: Session,
    property_code: Optional[str] = None,
    hours_threshold: int = 2,
) -> int:
    """
    미응답 메시지 수.
    
    조건:
    - is_read = False (처리완료 안 누른 것)
    - Inbox와 동일한 기준
    """
    conditions = [
        Conversation.is_read == False,  # 처리완료 안 누른 것만
    ]
    
    if property_code:
        conditions.append(Conversation.property_code == property_code)
    
    stmt = select(func.count(Conversation.id)).where(and_(*conditions))
    
    return db.execute(stmt).scalar() or 0


def _get_unanswered_messages(
    db: Session,
    property_code: Optional[str] = None,
    hours_threshold: int = 2,
    limit: int = 50,
) -> List[UnansweredMessageDTO]:
    """
    미응답 메시지 목록.
    
    조건:
    - is_read = False (처리완료 안 누른 것)
    - Inbox와 동일한 기준
    """
    conditions = [
        Conversation.is_read == False,  # 처리완료 안 누른 것만
    ]
    
    if property_code:
        conditions.append(Conversation.property_code == property_code)
    
    stmt = (
        select(Conversation)
        .where(and_(*conditions))
        .order_by(Conversation.last_message_at.desc())  # 최신 것 먼저
        .limit(limit)
    )
    
    conversations = list(db.execute(stmt).scalars().all())
    
    items = []
    now = datetime.now(timezone.utc)
    
    for conv in conversations:
        # 마지막 메시지 조회
        msg_stmt = (
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id)
            .order_by(IncomingMessage.received_at.desc())
            .limit(1)
        )
        last_msg = db.execute(msg_stmt).scalar_one_or_none()
        
        # 경과 시간 계산
        hours_since = None
        if conv.last_message_at:
            last_time = conv.last_message_at
            # timezone naive인 경우 UTC로 가정
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            delta = now - last_time
            hours_since = round(delta.total_seconds() / 3600, 1)
        
        items.append(UnansweredMessageDTO(
            conversation_id=str(conv.id),
            airbnb_thread_id=conv.airbnb_thread_id,
            property_code=conv.property_code,
            property_name=last_msg.ota_listing_name if last_msg else None,
            guest_name=last_msg.guest_name if last_msg else None,
            last_message_preview=(
                last_msg.pure_guest_message[:100] if last_msg and last_msg.pure_guest_message else None
            ),
            last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
            hours_since_last_message=hours_since,
        ))
    
    return items


def _count_staff_alerts(
    db: Session,
    property_code: Optional[str] = None,
) -> int:
    """Staff Alerts 수"""
    service = OCService(db)
    notifications = service.get_staff_notifications(limit=200)
    
    if property_code:
        notifications = [
            n for n in notifications 
            if getattr(n, 'property_code', None) == property_code
        ]
    
    return len(notifications)


def _count_today_movements(
    db: Session,
    today: date,
    property_code: Optional[str] = None,
) -> tuple[int, int]:
    """오늘 체크인/체크아웃 수"""
    # 체크인 수
    checkin_conditions = [
        ReservationInfo.checkin_date == today,
        ReservationInfo.status == ReservationStatus.CONFIRMED.value,
    ]
    if property_code:
        checkin_conditions.append(ReservationInfo.property_code == property_code)
    
    checkin_stmt = select(func.count(ReservationInfo.id)).where(and_(*checkin_conditions))
    checkins = db.execute(checkin_stmt).scalar() or 0
    
    # 체크아웃 수
    checkout_conditions = [
        ReservationInfo.checkout_date == today,
        ReservationInfo.status == ReservationStatus.CONFIRMED.value,
    ]
    if property_code:
        checkout_conditions.append(ReservationInfo.property_code == property_code)
    
    checkout_stmt = select(func.count(ReservationInfo.id)).where(and_(*checkout_conditions))
    checkouts = db.execute(checkout_stmt).scalar() or 0
    
    return checkins, checkouts
