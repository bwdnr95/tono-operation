# backend/app/api/v1/dashboard_analytics.py
"""
Dashboard Analytics API

예약 요청 데이터 기반 분석 엔드포인트:
- 전환율 분석 (숙소별)
- 응답 시간 분석
- 월별 트렌드
- 손실 매출 분석

설계:
- 기존 API 패턴 준수
- 타임존 비교는 func.now() 사용
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case, extract, and_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


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

class ConversionRateDTO(BaseModel):
    """전환율 DTO"""
    property_code: Optional[str]
    total_requests: int
    accepted: int
    declined: int
    expired: int
    pending: int
    conversion_rate: float  # accepted / total * 100


class ConversionRateResponse(BaseModel):
    """전환율 응답"""
    items: List[ConversionRateDTO]
    overall: ConversionRateDTO


class ResponseTimeDTO(BaseModel):
    """응답 시간 DTO"""
    property_code: Optional[str]
    avg_response_hours: Optional[float]
    min_response_hours: Optional[float]
    max_response_hours: Optional[float]
    total_responded: int


class ResponseTimeResponse(BaseModel):
    """응답 시간 응답"""
    items: List[ResponseTimeDTO]
    overall_avg_hours: Optional[float]


class MonthlyTrendDTO(BaseModel):
    """월별 트렌드 DTO"""
    month: str  # "2025-12"
    total_requests: int
    accepted: int
    declined: int
    expired: int
    conversion_rate: float
    total_expected_revenue: int
    accepted_revenue: int
    lost_revenue: int


class MonthlyTrendResponse(BaseModel):
    """월별 트렌드 응답"""
    items: List[MonthlyTrendDTO]


class LostRevenueDTO(BaseModel):
    """손실 매출 DTO"""
    property_code: Optional[str]
    listing_name: Optional[str]
    declined_count: int
    expired_count: int
    total_lost_count: int
    lost_revenue: int


class LostRevenueResponse(BaseModel):
    """손실 매출 응답"""
    items: List[LostRevenueDTO]
    total_lost_revenue: int
    total_lost_count: int


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/dashboard/analytics", tags=["Dashboard Analytics"])


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/conversion-rate", response_model=ConversionRateResponse)
def get_conversion_rate(
    days: int = Query(30, ge=1, le=365, description="최근 N일"),
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    db: Session = Depends(get_db),
) -> ConversionRateResponse:
    """
    예약 요청 전환율 분석.
    
    전환율 = 수락된 요청 / 전체 요청 * 100
    """
    try:
        from app.domain.models.pending_reservation_request import PendingReservationRequest
    except ImportError:
        logger.warning("PendingReservationRequest not found")
        return ConversionRateResponse(
            items=[],
            overall=ConversionRateDTO(
                property_code=None, total_requests=0, accepted=0,
                declined=0, expired=0, pending=0, conversion_rate=0.0
            )
        )
    
    since = func.now() - timedelta(days=days)
    
    conditions = [PendingReservationRequest.received_at >= since]
    if property_code:
        conditions.append(PendingReservationRequest.property_code == property_code)
    
    stmt = (
        select(
            PendingReservationRequest.property_code,
            func.count(PendingReservationRequest.id).label("total"),
            func.sum(case((PendingReservationRequest.status == "accepted", 1), else_=0)).label("accepted"),
            func.sum(case((PendingReservationRequest.status == "declined", 1), else_=0)).label("declined"),
            func.sum(case((PendingReservationRequest.status == "expired", 1), else_=0)).label("expired"),
            func.sum(case((PendingReservationRequest.status == "pending", 1), else_=0)).label("pending"),
        )
        .where(and_(*conditions))
        .group_by(PendingReservationRequest.property_code)
    )
    
    results = list(db.execute(stmt).all())
    
    items = []
    total_all = 0
    accepted_all = 0
    declined_all = 0
    expired_all = 0
    pending_all = 0
    
    for row in results:
        total = row.total or 0
        accepted = row.accepted or 0
        declined = row.declined or 0
        expired = row.expired or 0
        pending = row.pending or 0
        
        conversion_rate = (accepted / total * 100) if total > 0 else 0.0
        
        items.append(ConversionRateDTO(
            property_code=row.property_code,
            total_requests=total,
            accepted=accepted,
            declined=declined,
            expired=expired,
            pending=pending,
            conversion_rate=round(conversion_rate, 1),
        ))
        
        total_all += total
        accepted_all += accepted
        declined_all += declined
        expired_all += expired
        pending_all += pending
    
    overall_rate = (accepted_all / total_all * 100) if total_all > 0 else 0.0
    
    return ConversionRateResponse(
        items=items,
        overall=ConversionRateDTO(
            property_code=None,
            total_requests=total_all,
            accepted=accepted_all,
            declined=declined_all,
            expired=expired_all,
            pending=pending_all,
            conversion_rate=round(overall_rate, 1),
        ),
    )


@router.get("/response-time", response_model=ResponseTimeResponse)
def get_response_time(
    days: int = Query(30, ge=1, le=365, description="최근 N일"),
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    db: Session = Depends(get_db),
) -> ResponseTimeResponse:
    """
    응답 시간 분석.
    
    수락까지 걸린 평균/최소/최대 시간 (시간 단위).
    """
    try:
        from app.domain.models.pending_reservation_request import PendingReservationRequest
    except ImportError:
        logger.warning("PendingReservationRequest not found")
        return ResponseTimeResponse(items=[], overall_avg_hours=None)
    
    since = func.now() - timedelta(days=days)
    
    # 응답 시간 계산 (responded_at - received_at) in hours
    response_time_hours = (
        extract('epoch', PendingReservationRequest.responded_at) -
        extract('epoch', PendingReservationRequest.received_at)
    ) / 3600
    
    conditions = [
        PendingReservationRequest.received_at >= since,
        PendingReservationRequest.status == "accepted",
        PendingReservationRequest.responded_at.isnot(None),
        PendingReservationRequest.received_at.isnot(None),
    ]
    if property_code:
        conditions.append(PendingReservationRequest.property_code == property_code)
    
    stmt = (
        select(
            PendingReservationRequest.property_code,
            func.avg(response_time_hours).label("avg_hours"),
            func.min(response_time_hours).label("min_hours"),
            func.max(response_time_hours).label("max_hours"),
            func.count(PendingReservationRequest.id).label("count"),
        )
        .where(and_(*conditions))
        .group_by(PendingReservationRequest.property_code)
    )
    
    results = list(db.execute(stmt).all())
    
    items = []
    total_sum = 0.0
    total_count = 0
    
    for row in results:
        avg_hours = float(row.avg_hours) if row.avg_hours else None
        min_hours = float(row.min_hours) if row.min_hours else None
        max_hours = float(row.max_hours) if row.max_hours else None
        count = row.count or 0
        
        items.append(ResponseTimeDTO(
            property_code=row.property_code,
            avg_response_hours=round(avg_hours, 1) if avg_hours else None,
            min_response_hours=round(min_hours, 1) if min_hours else None,
            max_response_hours=round(max_hours, 1) if max_hours else None,
            total_responded=count,
        ))
        
        if avg_hours:
            total_sum += avg_hours * count
            total_count += count
    
    overall_avg = (total_sum / total_count) if total_count > 0 else None
    
    return ResponseTimeResponse(
        items=items,
        overall_avg_hours=round(overall_avg, 1) if overall_avg else None,
    )


@router.get("/monthly-trend", response_model=MonthlyTrendResponse)
def get_monthly_trend(
    months: int = Query(6, ge=1, le=24, description="최근 N개월"),
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    db: Session = Depends(get_db),
) -> MonthlyTrendResponse:
    """
    월별 예약 요청 트렌드.
    """
    try:
        from app.domain.models.pending_reservation_request import PendingReservationRequest
    except ImportError:
        logger.warning("PendingReservationRequest not found")
        return MonthlyTrendResponse(items=[])
    
    since = func.now() - timedelta(days=months * 30)
    
    # 월별 그룹핑
    month_expr = func.to_char(PendingReservationRequest.received_at, 'YYYY-MM')
    
    conditions = [PendingReservationRequest.received_at >= since]
    if property_code:
        conditions.append(PendingReservationRequest.property_code == property_code)
    
    stmt = (
        select(
            month_expr.label("month"),
            func.count(PendingReservationRequest.id).label("total"),
            func.sum(case((PendingReservationRequest.status == "accepted", 1), else_=0)).label("accepted"),
            func.sum(case((PendingReservationRequest.status == "declined", 1), else_=0)).label("declined"),
            func.sum(case((PendingReservationRequest.status == "expired", 1), else_=0)).label("expired"),
            func.coalesce(func.sum(PendingReservationRequest.expected_payout), 0).label("total_revenue"),
            func.coalesce(
                func.sum(case((PendingReservationRequest.status == "accepted", PendingReservationRequest.expected_payout), else_=0)),
                0
            ).label("accepted_revenue"),
            func.coalesce(
                func.sum(case((PendingReservationRequest.status.in_(["declined", "expired"]), PendingReservationRequest.expected_payout), else_=0)),
                0
            ).label("lost_revenue"),
        )
        .where(and_(*conditions))
        .group_by(month_expr)
        .order_by(month_expr)
    )
    
    results = list(db.execute(stmt).all())
    
    items = []
    for row in results:
        total = row.total or 0
        accepted = row.accepted or 0
        conversion_rate = (accepted / total * 100) if total > 0 else 0.0
        
        items.append(MonthlyTrendDTO(
            month=row.month or "",
            total_requests=total,
            accepted=accepted,
            declined=row.declined or 0,
            expired=row.expired or 0,
            conversion_rate=round(conversion_rate, 1),
            total_expected_revenue=row.total_revenue or 0,
            accepted_revenue=row.accepted_revenue or 0,
            lost_revenue=row.lost_revenue or 0,
        ))
    
    return MonthlyTrendResponse(items=items)


@router.get("/lost-revenue", response_model=LostRevenueResponse)
def get_lost_revenue(
    days: int = Query(30, ge=1, le=365, description="최근 N일"),
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    db: Session = Depends(get_db),
) -> LostRevenueResponse:
    """
    손실 매출 분석 (숙소별).
    
    거절/만료로 놓친 예상 매출 합계.
    """
    try:
        from app.domain.models.pending_reservation_request import PendingReservationRequest
    except ImportError:
        logger.warning("PendingReservationRequest not found")
        return LostRevenueResponse(items=[], total_lost_revenue=0, total_lost_count=0)
    
    since = func.now() - timedelta(days=days)
    
    conditions = [
        PendingReservationRequest.received_at >= since,
        PendingReservationRequest.status.in_(["declined", "expired"]),
    ]
    if property_code:
        conditions.append(PendingReservationRequest.property_code == property_code)
    
    stmt = (
        select(
            PendingReservationRequest.property_code,
            PendingReservationRequest.listing_name,
            func.sum(case((PendingReservationRequest.status == "declined", 1), else_=0)).label("declined"),
            func.sum(case((PendingReservationRequest.status == "expired", 1), else_=0)).label("expired"),
            func.count(PendingReservationRequest.id).label("total_lost"),
            func.coalesce(func.sum(PendingReservationRequest.expected_payout), 0).label("lost_revenue"),
        )
        .where(and_(*conditions))
        .group_by(
            PendingReservationRequest.property_code,
            PendingReservationRequest.listing_name,
        )
        .order_by(func.sum(PendingReservationRequest.expected_payout).desc().nullslast())
    )
    
    results = list(db.execute(stmt).all())
    
    items = []
    total_revenue = 0
    total_count = 0
    
    for row in results:
        lost_revenue = row.lost_revenue or 0
        lost_count = row.total_lost or 0
        
        items.append(LostRevenueDTO(
            property_code=row.property_code,
            listing_name=row.listing_name,
            declined_count=row.declined or 0,
            expired_count=row.expired or 0,
            total_lost_count=lost_count,
            lost_revenue=lost_revenue,
        ))
        
        total_revenue += lost_revenue
        total_count += lost_count
    
    return LostRevenueResponse(
        items=items,
        total_lost_revenue=total_revenue,
        total_lost_count=total_count,
    )
