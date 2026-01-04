# backend/app/api/v1/dashboard.py
"""
Dashboard API

운영 현황 요약:
- 예약 요청 (pending_reservation_requests)
- 미응답 메시지 (conversations where last_message is from guest)
- Staff Alerts (staff_notifications)
- 오늘 체크인/체크아웃
"""

from typing import Optional, List
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.db.session import get_db
from app.domain.models.conversation import Conversation
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.reservation_info import ReservationInfo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ============================================================
# Schemas
# ============================================================

class DashboardSummaryDTO(BaseModel):
    pending_reservations_count: int
    unanswered_messages_count: int
    staff_alerts_count: int
    today_checkins_count: int
    today_checkouts_count: int


class PendingReservationDTO(BaseModel):
    id: int
    reservation_code: Optional[str]
    guest_name: Optional[str]
    guest_verified: Optional[bool] = False
    guest_review_count: Optional[int] = 0
    guest_message: Optional[str]
    property_code: Optional[str]
    listing_name: Optional[str]
    checkin_date: Optional[str]
    checkout_date: Optional[str]
    nights: Optional[int]
    guest_count: Optional[int]
    expected_payout: Optional[float]
    action_url: Optional[str]
    remaining_hours: Optional[float]
    received_at: Optional[datetime]


class UnansweredMessageDTO(BaseModel):
    conversation_id: str
    airbnb_thread_id: Optional[str]
    guest_name: Optional[str]
    property_code: Optional[str]
    last_message_preview: Optional[str]
    last_message_at: Optional[datetime]
    hours_since_last_message: float


class StaffAlertDTO(BaseModel):
    oc_id: str
    conversation_id: Optional[str]
    airbnb_thread_id: Optional[str]
    property_code: Optional[str]
    property_name: Optional[str]
    guest_name: Optional[str]
    topic: str
    description: str
    target_date: Optional[str]
    status: Optional[str]
    priority: str
    created_at: Optional[datetime]


class PendingReservationsResponse(BaseModel):
    items: List[PendingReservationDTO]
    total: int


class UnansweredMessagesResponse(BaseModel):
    items: List[UnansweredMessageDTO]
    total: int


class StaffAlertsResponse(BaseModel):
    items: List[StaffAlertDTO]
    total: int


# ============================================================
# Endpoints
# ============================================================

@router.get("/summary", response_model=DashboardSummaryDTO)
def get_dashboard_summary(db: Session = Depends(get_db)):
    """대시보드 요약 정보"""
    from app.domain.models.reservation_info import ReservationStatus
    
    today = date.today()
    
    # 1. 예약 요청 (reservation_info.status = 'awaiting_approval')
    pending_reservations_count = db.query(func.count(ReservationInfo.id)).filter(
        ReservationInfo.status == ReservationStatus.AWAITING_APPROVAL.value
    ).scalar() or 0
    
    # 2. 미응답 메시지 (is_read=False인 conversation 중 마지막 메시지가 guest인 것)
    unanswered_messages_count = db.query(func.count(Conversation.id)).filter(
        Conversation.is_read == False
    ).scalar() or 0
    
    # 3. Staff Alerts (미해결) - OCService와 동일한 로직 사용
    from app.services.oc_service import OCService
    staff_alerts = OCService(db).get_staff_notifications(today=today, limit=100)
    staff_alerts_count = len(staff_alerts)
    
    # 4. 오늘 체크인
    today_checkins_count = db.query(func.count(ReservationInfo.id)).filter(
        ReservationInfo.checkin_date == today
    ).scalar() or 0
    
    # 5. 오늘 체크아웃
    today_checkouts_count = db.query(func.count(ReservationInfo.id)).filter(
        ReservationInfo.checkout_date == today
    ).scalar() or 0
    
    return DashboardSummaryDTO(
        pending_reservations_count=pending_reservations_count,
        unanswered_messages_count=unanswered_messages_count,
        staff_alerts_count=staff_alerts_count,
        today_checkins_count=today_checkins_count,
        today_checkouts_count=today_checkouts_count,
    )


@router.get("/pending-requests", response_model=PendingReservationsResponse)
def get_pending_reservations(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """예약 요청 목록 (reservation_info.status = 'awaiting_approval')"""
    from app.domain.models.reservation_info import ReservationStatus
    from datetime import timezone
    
    rows = db.query(ReservationInfo).filter(
        ReservationInfo.status == ReservationStatus.AWAITING_APPROVAL.value
    ).order_by(
        ReservationInfo.expires_at.asc().nullslast()
    ).limit(limit).all()
    
    now = datetime.now(timezone.utc)
    items = []
    
    for r in rows:
        remaining_hours = None
        if r.expires_at:
            # timezone-aware 비교
            expires_at = r.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            delta = expires_at - now
            remaining_hours = delta.total_seconds() / 3600
        
        items.append(PendingReservationDTO(
            id=r.id,
            reservation_code=r.reservation_code,
            guest_name=r.guest_name,
            guest_verified=False,  # reservation_info에 없음
            guest_review_count=0,  # reservation_info에 없음
            guest_message=r.guest_message,
            property_code=r.property_code,
            listing_name=r.listing_name,
            checkin_date=str(r.checkin_date) if r.checkin_date else None,
            checkout_date=str(r.checkout_date) if r.checkout_date else None,
            nights=r.nights,
            guest_count=r.guest_count,
            expected_payout=float(r.host_payout) if r.host_payout else None,
            action_url=r.action_url,  # DB에서 직접 가져옴
            remaining_hours=remaining_hours,
            received_at=r.created_at,
        ))
    
    return PendingReservationsResponse(items=items, total=len(items))


@router.get("/unanswered-messages", response_model=UnansweredMessagesResponse)
def get_unanswered_messages(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """미응답 메시지 목록"""
    now = datetime.utcnow()
    
    # is_read=False인 conversation들
    conversations = db.query(Conversation).filter(
        Conversation.is_read == False
    ).order_by(
        Conversation.last_message_at.desc()
    ).limit(limit).all()
    
    items = []
    for c in conversations:
        # 마지막 메시지 가져오기
        last_msg = db.query(IncomingMessage).filter(
            IncomingMessage.airbnb_thread_id == c.airbnb_thread_id
        ).order_by(
            IncomingMessage.received_at.desc()
        ).first()
        
        hours_since = 0
        preview = None
        guest_name = None
        
        if last_msg:
            if last_msg.received_at:
                delta = now - last_msg.received_at.replace(tzinfo=None)
                hours_since = delta.total_seconds() / 3600
            preview = (last_msg.pure_guest_message or last_msg.content or "")[:100]
            guest_name = last_msg.guest_name
        
        # reservation_info에서 guest_name 보완
        if not guest_name:
            res_info = db.query(ReservationInfo).filter(
                ReservationInfo.airbnb_thread_id == c.airbnb_thread_id
            ).first()
            if res_info:
                guest_name = res_info.guest_name
        
        items.append(UnansweredMessageDTO(
            conversation_id=str(c.id),
            airbnb_thread_id=c.airbnb_thread_id,
            guest_name=guest_name,
            property_code=c.property_code,
            last_message_preview=preview,
            last_message_at=c.last_message_at,
            hours_since_last_message=round(hours_since, 1),
        ))
    
    return UnansweredMessagesResponse(items=items, total=len(items))


@router.get("/staff-alerts", response_model=StaffAlertsResponse)
def get_staff_alerts(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Staff Alerts 목록 - OCService와 동일한 로직 사용"""
    from datetime import date as date_type
    from app.services.oc_service import OCService
    
    today = date_type.today()
    items_from_service = OCService(db).get_staff_notifications(today=today, limit=limit)
    
    items = []
    for item in items_from_service:
        # property_code, property_name 조회
        property_code = None
        property_name = None
        airbnb_thread_id = None
        if item.conversation_id:
            conv = db.query(Conversation).filter(
                Conversation.id == item.conversation_id
            ).first()
            if conv:
                property_code = conv.property_code
                airbnb_thread_id = conv.airbnb_thread_id
                # property_name은 property_profiles에서 조회 가능하면 추가
        
        items.append(StaffAlertDTO(
            oc_id=str(item.oc_id),
            conversation_id=str(item.conversation_id) if item.conversation_id else None,
            airbnb_thread_id=airbnb_thread_id,
            property_code=property_code,
            property_name=item.property_name if hasattr(item, 'property_name') else None,
            guest_name=item.guest_name,
            topic=item.topic,
            description=item.description,
            target_date=str(item.target_date) if item.target_date else None,
            status=item.status,
            priority=item.priority.value if hasattr(item.priority, 'value') else str(item.priority),
            created_at=item.created_at,
        ))
    
    return StaffAlertsResponse(items=items, total=len(items))


# ============================================================
# 예약 요청 처리
# ============================================================

@router.patch("/pending-reservations/{reservation_id}/decline")
def decline_pending_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
):
    """
    예약 요청 거절 처리.
    
    에어비앤비에서 거절한 후, 수동으로 상태를 업데이트할 때 사용.
    status를 'declined'로 변경하여 대기 목록에서 제거.
    """
    from app.repositories.reservation_info_repository import ReservationInfoRepository
    from app.domain.models.reservation_info import ReservationStatus
    
    repo = ReservationInfoRepository(db)
    
    # 상태 변경
    updated = repo.set_status(reservation_id, ReservationStatus.DECLINED.value)
    
    if not updated:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="예약 요청을 찾을 수 없습니다")
    
    db.commit()
    
    return {
        "success": True,
        "message": "거절 처리되었습니다",
        "reservation_id": reservation_id,
        "status": ReservationStatus.DECLINED.value,
    }
