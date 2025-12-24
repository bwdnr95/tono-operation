"""
Staff Notification & Operational Commitment API

Staff Notification = OC 기반
"약속 존재"가 아니라 "운영 리스크 발생 시점"만 노출

Endpoints:
- GET /staff-notifications - Action Queue (노출 대상 OC)
- GET /staff-notifications/{oc_id} - 단일 OC 조회
- POST /staff-notifications/{oc_id}/done - 완료 처리
- POST /staff-notifications/{oc_id}/confirm-resolve - suggested_resolve 확정
- POST /staff-notifications/{oc_id}/reject-resolve - suggested_resolve 거부
- POST /staff-notifications/{oc_id}/confirm-candidate - 후보 확정
- POST /staff-notifications/{oc_id}/reject-candidate - 후보 거부
- GET /conversations/{airbnb_thread_id}/ocs - Conversation의 OC 목록 (Backlog)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.models.conversation import Conversation
from app.domain.models.operational_commitment import (
    OperationalCommitment,
    OCStatus,
    OCPriority,
    StaffNotificationItem,
)
from app.services.oc_service import OCService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# DB Session
# ─────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# DTOs
# ─────────────────────────────────────────────────────────────

class OCDTO(BaseModel):
    id: str
    conversation_id: str
    topic: str
    description: str
    evidence_quote: str
    target_time_type: str
    target_date: Optional[str]
    status: str
    resolution_reason: Optional[str]
    resolution_evidence: Optional[str]  # 해소 제안 근거 (게스트 메시지)
    is_candidate_only: bool
    created_at: str
    
    class Config:
        from_attributes = True


class OCListResponse(BaseModel):
    airbnb_thread_id: str
    items: List[OCDTO]
    total: int


class StaffNotificationDTO(BaseModel):
    """Staff Notification 항목 (Action Queue용)"""
    oc_id: str
    conversation_id: str
    airbnb_thread_id: str
    topic: str
    description: str
    evidence_quote: str
    priority: str  # immediate, upcoming, pending
    guest_name: Optional[str]
    checkin_date: Optional[str]
    checkout_date: Optional[str]
    property_code: Optional[str]      # 🆕 숙소 코드
    property_name: Optional[str]      # 🆕 숙소명
    status: str
    resolution_reason: Optional[str]
    resolution_evidence: Optional[str]  # 해소 제안 근거 (게스트 메시지)
    is_candidate_only: bool
    target_time_type: str
    target_date: Optional[str]
    created_at: Optional[str]


class StaffNotificationListResponse(BaseModel):
    items: List[StaffNotificationDTO]
    total: int
    as_of: str  # 조회 기준 날짜


class OCActionResponse(BaseModel):
    oc_id: str
    status: str
    action: str
    success: bool


# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/staff-notifications", tags=["staff-notifications"])


# ─────────────────────────────────────────────────────────────
# Staff Notification Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("", response_model=StaffNotificationListResponse)
def get_staff_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Staff Notification Action Queue
    
    지금 처리해야 할 OC 목록 (노출 조건 만족하는 것만)
    
    노출 규칙:
    - status = pending or suggested_resolve
    - explicit: D-1부터 노출
    - implicit: 즉시 노출
    - 체류 중: 최상단 고정
    """
    today = date.today()
    service = OCService(db)
    
    items = service.get_staff_notifications(today=today, limit=limit)
    
    return StaffNotificationListResponse(
        items=[
            StaffNotificationDTO(
                oc_id=str(item.oc_id),
                conversation_id=str(item.conversation_id),
                airbnb_thread_id=item.airbnb_thread_id,
                topic=item.topic,
                description=item.description,
                evidence_quote=item.evidence_quote,
                priority=item.priority.value,
                guest_name=item.guest_name,
                checkin_date=item.checkin_date.isoformat() if item.checkin_date else None,
                checkout_date=item.checkout_date.isoformat() if item.checkout_date else None,
                property_code=item.property_code,
                property_name=item.property_name,
                status=item.status,
                resolution_reason=item.resolution_reason,
                resolution_evidence=item.resolution_evidence,
                is_candidate_only=item.is_candidate_only,
                target_time_type=item.target_time_type,
                target_date=item.target_date.isoformat() if item.target_date else None,
                created_at=item.created_at.isoformat() if item.created_at else None,
            )
            for item in items
        ],
        total=len(items),
        as_of=today.isoformat(),
    )


@router.get("/{oc_id}", response_model=OCDTO)
def get_staff_notification(
    oc_id: UUID,
    db: Session = Depends(get_db),
):
    """단일 OC 조회"""
    from app.repositories.oc_repository import OCRepository
    
    repo = OCRepository(db)
    oc = repo.get_by_id(oc_id)
    
    if not oc:
        raise HTTPException(status_code=404, detail="OC not found")
    
    return OCDTO(
        id=str(oc.id),
        conversation_id=str(oc.conversation_id),
        topic=oc.topic,
        description=oc.description,
        evidence_quote=oc.evidence_quote,
        target_time_type=oc.target_time_type,
        target_date=oc.target_date.isoformat() if oc.target_date else None,
        status=oc.status,
        resolution_reason=oc.resolution_reason,
        is_candidate_only=oc.is_candidate_only,
        created_at=oc.created_at.isoformat() if oc.created_at else None,
    )


# ─────────────────────────────────────────────────────────────
# OC Action Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/{oc_id}/done", response_model=OCActionResponse)
def mark_oc_done(
    oc_id: UUID,
    db: Session = Depends(get_db),
):
    """
    OC 완료 처리
    
    운영 액션을 수행했을 때 호출
    """
    service = OCService(db)
    oc = service.mark_done(oc_id, by="host")
    
    if not oc:
        raise HTTPException(status_code=404, detail="OC not found")
    
    return OCActionResponse(
        oc_id=str(oc_id),
        status=oc.status,
        action="done",
        success=True,
    )


@router.post("/{oc_id}/confirm-resolve", response_model=OCActionResponse)
def confirm_oc_resolve(
    oc_id: UUID,
    db: Session = Depends(get_db),
):
    """
    suggested_resolve 확정
    
    시스템이 제안한 해소를 운영자가 1클릭으로 확정
    """
    service = OCService(db)
    oc = service.confirm_resolve(oc_id, by="host")
    
    if not oc:
        raise HTTPException(status_code=404, detail="OC not found or not in suggested_resolve status")
    
    return OCActionResponse(
        oc_id=str(oc_id),
        status=oc.status,
        action="confirm_resolve",
        success=True,
    )


@router.post("/{oc_id}/reject-resolve", response_model=OCActionResponse)
def reject_oc_resolve(
    oc_id: UUID,
    db: Session = Depends(get_db),
):
    """
    suggested_resolve 거부
    
    시스템 제안을 거부하고 pending으로 복귀
    """
    service = OCService(db)
    oc = service.reject_resolve(oc_id)
    
    if not oc:
        raise HTTPException(status_code=404, detail="OC not found")
    
    return OCActionResponse(
        oc_id=str(oc_id),
        status=oc.status,
        action="reject_resolve",
        success=True,
    )


@router.post("/{oc_id}/confirm-candidate", response_model=OCActionResponse)
def confirm_oc_candidate(
    oc_id: UUID,
    db: Session = Depends(get_db),
):
    """
    후보 확정
    
    refund/payment/compensation 등 운영자 확정 필요한 OC 확정
    """
    service = OCService(db)
    oc = service.confirm_candidate(oc_id)
    
    if not oc:
        raise HTTPException(status_code=404, detail="OC not found or not a candidate")
    
    return OCActionResponse(
        oc_id=str(oc_id),
        status=oc.status,
        action="confirm_candidate",
        success=True,
    )


@router.post("/{oc_id}/reject-candidate", response_model=OCActionResponse)
def reject_oc_candidate(
    oc_id: UUID,
    db: Session = Depends(get_db),
):
    """
    후보 거부
    
    잘못 추출된 OC 후보 거부
    """
    service = OCService(db)
    oc = service.reject_candidate(oc_id)
    
    if not oc:
        raise HTTPException(status_code=404, detail="OC not found or not a candidate")
    
    return OCActionResponse(
        oc_id=str(oc_id),
        status=oc.status,
        action="reject_candidate",
        success=True,
    )


# ─────────────────────────────────────────────────────────────
# Conversation OC Endpoints (Backlog)
# ─────────────────────────────────────────────────────────────

@router.get("/conversations/{airbnb_thread_id}/ocs", response_model=OCListResponse)
def get_conversation_ocs(
    airbnb_thread_id: str,
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Conversation의 OC 목록 조회
    
    Backlog 화면용 - 전체 OC 조회 가능
    """
    # Conversation 조회
    conv = db.execute(
        select(Conversation).where(Conversation.airbnb_thread_id == airbnb_thread_id)
    ).scalar_one_or_none()
    
    if not conv:
        return OCListResponse(
            airbnb_thread_id=airbnb_thread_id,
            items=[],
            total=0,
        )
    
    service = OCService(db)
    ocs = service.get_conversation_ocs(
        conversation_id=conv.id,
        include_resolved=include_resolved,
    )
    
    return OCListResponse(
        airbnb_thread_id=airbnb_thread_id,
        items=[
            OCDTO(
                id=str(oc.id),
                conversation_id=str(oc.conversation_id),
                topic=oc.topic,
                description=oc.description,
                evidence_quote=oc.evidence_quote,
                target_time_type=oc.target_time_type,
                target_date=oc.target_date.isoformat() if oc.target_date else None,
                status=oc.status,
                resolution_reason=oc.resolution_reason,
                is_candidate_only=oc.is_candidate_only,
                created_at=oc.created_at.isoformat() if oc.created_at else None,
            )
            for oc in ocs
        ],
        total=len(ocs),
    )
