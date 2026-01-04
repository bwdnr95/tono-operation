# backend/app/api/v1/complaints.py
"""
Complaint API

게스트 불만/문제 관리 엔드포인트
- 목록 조회 (필터링)
- 상세 조회
- 상태 변경 (resolve, dismiss)
- Analytics (숙소별 히트맵)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.models.complaint import (
    Complaint,
    ComplaintCategory,
    ComplaintSeverity,
    ComplaintStatus,
    COMPLAINT_CATEGORY_LABELS,
    COMPLAINT_SEVERITY_LABELS,
    COMPLAINT_STATUS_LABELS,
)
from app.domain.models.conversation import Conversation
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.property_profile import PropertyProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/complaints", tags=["Complaints"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# DTOs
# ═══════════════════════════════════════════════════════════════

class ComplaintDTO(BaseModel):
    id: str
    conversation_id: str
    category: str
    category_label: str
    severity: str
    severity_label: str
    description: str
    evidence_quote: Optional[str]
    status: str
    status_label: str
    resolution_note: Optional[str]
    property_code: str
    property_name: Optional[str]
    guest_name: Optional[str]
    reported_at: datetime
    resolved_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ComplaintListResponse(BaseModel):
    items: List[ComplaintDTO]
    total: int


class ResolveComplaintRequest(BaseModel):
    resolution_note: str


class DismissComplaintRequest(BaseModel):
    reason: str


# ═══════════════════════════════════════════════════════════════
# Complaint CRUD
# ═══════════════════════════════════════════════════════════════

@router.get("", response_model=ComplaintListResponse)
def list_complaints(
    status: Optional[str] = Query(None, description="open|in_progress|resolved|dismissed"),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    property_code: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
) -> ComplaintListResponse:
    """Complaint 목록 조회"""
    
    conditions = []
    
    if status:
        conditions.append(Complaint.status == status)
    if category:
        conditions.append(Complaint.category == category)
    if severity:
        conditions.append(Complaint.severity == severity)
    if property_code:
        conditions.append(Complaint.property_code == property_code)
    if start_date:
        conditions.append(Complaint.reported_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        conditions.append(Complaint.reported_at <= datetime.combine(end_date, datetime.max.time()))
    
    # 총 건수
    total_query = select(func.count(Complaint.id))
    if conditions:
        total_query = total_query.where(and_(*conditions))
    total = db.execute(total_query).scalar() or 0
    
    # 목록 조회
    query = select(Complaint).order_by(Complaint.reported_at.desc())
    if conditions:
        query = query.where(and_(*conditions))
    query = query.limit(limit).offset(offset)
    
    complaints = db.execute(query).scalars().all()
    
    items = []
    for c in complaints:
        # Property 이름
        prop_name = None
        if c.property_code:
            prop = db.execute(
                select(PropertyProfile.name).where(PropertyProfile.property_code == c.property_code)
            ).scalar()
            prop_name = prop
        
        # Guest 이름 (provenance_message에서)
        guest_name = None
        if c.provenance_message_id:
            msg = db.execute(
                select(IncomingMessage.guest_name).where(IncomingMessage.id == c.provenance_message_id)
            ).scalar()
            guest_name = msg
        
        items.append(ComplaintDTO(
            id=str(c.id),
            conversation_id=str(c.conversation_id),
            category=c.category,
            category_label=COMPLAINT_CATEGORY_LABELS.get(c.category, c.category),
            severity=c.severity,
            severity_label=COMPLAINT_SEVERITY_LABELS.get(c.severity, c.severity),
            description=c.description,
            evidence_quote=c.evidence_quote,
            status=c.status,
            status_label=COMPLAINT_STATUS_LABELS.get(c.status, c.status),
            resolution_note=c.resolution_note,
            property_code=c.property_code,
            property_name=prop_name,
            guest_name=guest_name,
            reported_at=c.reported_at,
            resolved_at=c.resolved_at,
        ))
    
    return ComplaintListResponse(items=items, total=total)


@router.get("/{complaint_id}", response_model=ComplaintDTO)
def get_complaint(
    complaint_id: UUID,
    db: Session = Depends(get_db),
) -> ComplaintDTO:
    """Complaint 상세 조회"""
    
    c = db.execute(
        select(Complaint).where(Complaint.id == complaint_id)
    ).scalar()
    
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Property 이름
    prop_name = None
    if c.property_code:
        prop = db.execute(
            select(PropertyProfile.name).where(PropertyProfile.property_code == c.property_code)
        ).scalar()
        prop_name = prop
    
    # Guest 이름
    guest_name = None
    if c.provenance_message_id:
        msg = db.execute(
            select(IncomingMessage.guest_name).where(IncomingMessage.id == c.provenance_message_id)
        ).scalar()
        guest_name = msg
    
    return ComplaintDTO(
        id=str(c.id),
        conversation_id=str(c.conversation_id),
        category=c.category,
        category_label=COMPLAINT_CATEGORY_LABELS.get(c.category, c.category),
        severity=c.severity,
        severity_label=COMPLAINT_SEVERITY_LABELS.get(c.severity, c.severity),
        description=c.description,
        evidence_quote=c.evidence_quote,
        status=c.status,
        status_label=COMPLAINT_STATUS_LABELS.get(c.status, c.status),
        resolution_note=c.resolution_note,
        property_code=c.property_code,
        property_name=prop_name,
        guest_name=guest_name,
        reported_at=c.reported_at,
        resolved_at=c.resolved_at,
    )


@router.post("/{complaint_id}/resolve")
def resolve_complaint(
    complaint_id: UUID,
    body: ResolveComplaintRequest,
    db: Session = Depends(get_db),
):
    """Complaint 해결 처리"""
    
    c = db.execute(
        select(Complaint).where(Complaint.id == complaint_id)
    ).scalar()
    
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    c.resolve(note=body.resolution_note, resolved_by="host")
    db.commit()
    
    return {"success": True, "status": c.status}


@router.post("/{complaint_id}/dismiss")
def dismiss_complaint(
    complaint_id: UUID,
    body: DismissComplaintRequest,
    db: Session = Depends(get_db),
):
    """Complaint 기각 (해당없음)"""
    
    c = db.execute(
        select(Complaint).where(Complaint.id == complaint_id)
    ).scalar()
    
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    c.dismiss(reason=body.reason, dismissed_by="host")
    db.commit()
    
    return {"success": True, "status": c.status}


@router.post("/{complaint_id}/in-progress")
def start_progress(
    complaint_id: UUID,
    db: Session = Depends(get_db),
):
    """Complaint 처리 중 상태로 변경"""
    
    c = db.execute(
        select(Complaint).where(Complaint.id == complaint_id)
    ).scalar()
    
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    c.start_progress()
    db.commit()
    
    return {"success": True, "status": c.status}


# ═══════════════════════════════════════════════════════════════
# Complaint Analytics (숙소별 히트맵)
# ═══════════════════════════════════════════════════════════════

class ComplaintHeatmapCellDTO(BaseModel):
    category: str
    category_label: str
    count: int


class ComplaintHeatmapRowDTO(BaseModel):
    property_code: str
    property_name: Optional[str]
    total_count: int
    cells: List[ComplaintHeatmapCellDTO]


class ComplaintHeatmapResponse(BaseModel):
    categories: List[str]
    category_labels: Dict[str, str]
    rows: List[ComplaintHeatmapRowDTO]
    period_start: Optional[date]
    period_end: Optional[date]


@router.get("/analytics/heatmap", response_model=ComplaintHeatmapResponse)
def get_complaint_heatmap(
    period: str = Query("month", description="week|month|quarter|year|all|custom"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> ComplaintHeatmapResponse:
    """
    숙소별 x 카테고리별 Complaint 히트맵
    
    운영 지표: 어떤 숙소에서 어떤 유형의 문제가 자주 발생하는지 파악
    """
    
    # 기간 계산
    today = date.today()
    if period == "week":
        period_start = today - timedelta(days=7)
        period_end = today
    elif period == "month":
        period_start = today - timedelta(days=30)
        period_end = today
    elif period == "quarter":
        period_start = today - timedelta(days=90)
        period_end = today
    elif period == "year":
        period_start = today - timedelta(days=365)
        period_end = today
    elif period == "custom" and start_date and end_date:
        period_start = start_date
        period_end = end_date
    else:  # all
        period_start = None
        period_end = None
    
    # 기간 조건
    date_conditions = []
    if period_start:
        date_conditions.append(Complaint.reported_at >= datetime.combine(period_start, datetime.min.time()))
    if period_end:
        date_conditions.append(Complaint.reported_at <= datetime.combine(period_end, datetime.max.time()))
    
    # 전체 카테고리 목록 (데이터가 있는 것만)
    cat_query = select(Complaint.category).distinct()
    if date_conditions:
        cat_query = cat_query.where(and_(*date_conditions))
    all_categories = db.execute(cat_query.order_by(Complaint.category)).scalars().all()
    
    if not all_categories:
        return ComplaintHeatmapResponse(
            categories=[],
            category_labels=COMPLAINT_CATEGORY_LABELS,
            rows=[],
            period_start=period_start,
            period_end=period_end,
        )
    
    # 모든 property 가져오기
    properties = db.execute(
        select(PropertyProfile.property_code, PropertyProfile.name)
    ).all()
    
    rows = []
    
    for code, name in properties:
        # 기간 + 숙소 조건
        conditions = [Complaint.property_code == code]
        if date_conditions:
            conditions.extend(date_conditions)
        
        # 숙소별 전체 건수
        total_count = db.execute(
            select(func.count(Complaint.id)).where(and_(*conditions))
        ).scalar() or 0
        
        if total_count == 0:
            continue
        
        # 카테고리별 건수
        cat_counts = db.execute(
            select(
                Complaint.category,
                func.count(Complaint.id).label("count")
            )
            .where(and_(*conditions))
            .group_by(Complaint.category)
        ).all()
        
        cat_count_map = {cat: count for cat, count in cat_counts}
        
        # 모든 카테고리에 대해 셀 생성
        cells = []
        for cat in all_categories:
            cells.append(ComplaintHeatmapCellDTO(
                category=cat,
                category_label=COMPLAINT_CATEGORY_LABELS.get(cat, cat),
                count=cat_count_map.get(cat, 0),
            ))
        
        rows.append(ComplaintHeatmapRowDTO(
            property_code=code,
            property_name=name,
            total_count=total_count,
            cells=cells,
        ))
    
    # 총 건수 기준 내림차순 정렬
    rows.sort(key=lambda x: x.total_count, reverse=True)
    
    return ComplaintHeatmapResponse(
        categories=list(all_categories),
        category_labels=COMPLAINT_CATEGORY_LABELS,
        rows=rows,
        period_start=period_start,
        period_end=period_end,
    )


# ═══════════════════════════════════════════════════════════════
# Complaint 상세 목록 (드릴다운)
# ═══════════════════════════════════════════════════════════════

class ComplaintDetailItemDTO(BaseModel):
    id: str
    conversation_id: str
    description: str
    evidence_quote: Optional[str]
    severity: str
    severity_label: str
    status: str
    status_label: str
    guest_name: Optional[str]
    reported_at: datetime
    resolved_at: Optional[datetime]


class ComplaintDetailListResponse(BaseModel):
    property_code: str
    property_name: Optional[str]
    category: str
    category_label: str
    total_count: int
    items: List[ComplaintDetailItemDTO]


@router.get("/analytics/detail/{property_code}/{category}", response_model=ComplaintDetailListResponse)
def get_complaint_detail_list(
    property_code: str,
    category: str,
    period: str = Query("month"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> ComplaintDetailListResponse:
    """
    특정 숙소 + 카테고리의 Complaint 상세 목록
    
    히트맵에서 클릭 시 실제 어떤 문제들이 발생했는지 확인
    """
    
    # 기간 계산
    today = date.today()
    if period == "week":
        period_start = today - timedelta(days=7)
        period_end = today
    elif period == "month":
        period_start = today - timedelta(days=30)
        period_end = today
    elif period == "quarter":
        period_start = today - timedelta(days=90)
        period_end = today
    elif period == "year":
        period_start = today - timedelta(days=365)
        period_end = today
    elif period == "custom" and start_date and end_date:
        period_start = start_date
        period_end = end_date
    else:
        period_start = None
        period_end = None
    
    # Property 이름
    prop_name = db.execute(
        select(PropertyProfile.name).where(PropertyProfile.property_code == property_code)
    ).scalar()
    
    # 조건
    conditions = [
        Complaint.property_code == property_code,
        Complaint.category == category,
    ]
    if period_start:
        conditions.append(Complaint.reported_at >= datetime.combine(period_start, datetime.min.time()))
    if period_end:
        conditions.append(Complaint.reported_at <= datetime.combine(period_end, datetime.max.time()))
    
    # 목록 조회
    complaints = db.execute(
        select(Complaint)
        .where(and_(*conditions))
        .order_by(Complaint.reported_at.desc())
    ).scalars().all()
    
    items = []
    for c in complaints:
        # Guest 이름
        guest_name = None
        if c.provenance_message_id:
            msg = db.execute(
                select(IncomingMessage.guest_name).where(IncomingMessage.id == c.provenance_message_id)
            ).scalar()
            guest_name = msg
        
        items.append(ComplaintDetailItemDTO(
            id=str(c.id),
            conversation_id=str(c.conversation_id),
            description=c.description,
            evidence_quote=c.evidence_quote,
            severity=c.severity,
            severity_label=COMPLAINT_SEVERITY_LABELS.get(c.severity, c.severity),
            status=c.status,
            status_label=COMPLAINT_STATUS_LABELS.get(c.status, c.status),
            guest_name=guest_name,
            reported_at=c.reported_at,
            resolved_at=c.resolved_at,
        ))
    
    return ComplaintDetailListResponse(
        property_code=property_code,
        property_name=prop_name,
        category=category,
        category_label=COMPLAINT_CATEGORY_LABELS.get(category, category),
        total_count=len(items),
        items=items,
    )
