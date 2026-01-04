# backend/app/api/v1/analytics.py
"""
Analytics API

운영 성과 분석 엔드포인트:
- 예약 확정 건수
- 메시지 발송 건수
- 평균 응답 시간
- AI 채택률
- 예약 리드타임
- ADR (Average Daily Rate)
- 점유율 (iCal + reservation_info 연동)
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, case, and_, extract
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
from app.domain.models.ical_blocked_date import IcalBlockedDate
from app.domain.models.property_profile import PropertyProfile

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

class AnalyticsSummaryDTO(BaseModel):
    """기간별 분석 요약"""
    # 기간 정보
    period: str  # "today", "week", "month", "custom"
    start_date: date
    end_date: date
    
    # 운영 지표
    reservations_confirmed: int  # 예약 확정 건수
    messages_sent: int  # 메시지 발송 건수
    avg_response_minutes: Optional[float]  # 평균 응답 시간 (분)
    ai_adoption_rate: Optional[float]  # AI 채택률 (%)
    
    # 수익 지표
    lead_time_days: Optional[float]  # 예약 리드타임 (일)
    adr: Optional[int]  # ADR (원)
    occupancy_rate: Optional[float]  # 점유율 (%) - iCal 연동 후
    
    # 비교 (이전 기간 대비)
    reservations_confirmed_change: Optional[float]  # %
    messages_sent_change: Optional[float]  # %
    avg_response_change: Optional[float]  # 분
    ai_adoption_change: Optional[float]  # %p


class TrendItemDTO(BaseModel):
    """월별 트렌드 아이템"""
    month: str  # "2025-12"
    
    # 운영 지표
    reservations_confirmed: int
    messages_sent: int
    avg_response_minutes: Optional[float]
    ai_adoption_rate: Optional[float]
    
    # 수익 지표
    lead_time_days: Optional[float]
    adr: Optional[int]
    occupancy_rate: Optional[float]


class TrendResponse(BaseModel):
    """월별 트렌드 응답"""
    items: List[TrendItemDTO]


class PropertyComparisonDTO(BaseModel):
    """숙소별 비교"""
    property_code: str
    property_name: Optional[str]
    
    reservations_confirmed: int
    messages_sent: int
    avg_response_minutes: Optional[float]
    ai_adoption_rate: Optional[float]
    lead_time_days: Optional[float]
    adr: Optional[int]
    occupancy_rate: Optional[float]


class PropertyComparisonResponse(BaseModel):
    """숙소별 비교 응답"""
    items: List[PropertyComparisonDTO]


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# =============================================================================
# Helper Functions
# =============================================================================

def get_date_range(period: str, start_date: Optional[date], end_date: Optional[date]) -> tuple[date, date]:
    """기간 문자열을 날짜 범위로 변환"""
    today = date.today()
    
    if period == "today":
        return today, today
    elif period == "week":
        start = today - timedelta(days=today.weekday())  # 이번 주 월요일
        return start, today
    elif period == "month":
        start = today.replace(day=1)  # 이번 달 1일
        return start, today
    elif period == "custom":
        if not start_date or not end_date:
            raise HTTPException(400, "custom 기간은 start_date와 end_date 필수")
        return start_date, end_date
    else:
        raise HTTPException(400, f"Invalid period: {period}")


def get_previous_period(start_date: date, end_date: date) -> tuple[date, date]:
    """이전 동일 기간 계산"""
    days = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start, prev_end


def calc_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """변화율 계산 (%)"""
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def calc_diff(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """차이 계산"""
    if current is None or previous is None:
        return None
    return round(current - previous, 1)


def calc_occupancy_rate(
    db: Session,
    start_date: date,
    end_date: date,
    property_code: Optional[str] = None,
) -> Optional[float]:
    """
    점유율 계산 (예약 + iCal 차단)
    
    Args:
        db: DB 세션
        start_date: 시작일 (inclusive)
        end_date: 종료일 (inclusive)
        property_code: 특정 숙소만 계산 (None이면 전체)
    
    Returns:
        점유율 (%) or None
    """
    total_days = (end_date - start_date).days + 1
    if total_days <= 0:
        return None
    
    # property_code 목록 가져오기
    if property_code:
        property_codes = [property_code]
    else:
        codes = db.execute(
            select(PropertyProfile.property_code).where(
                PropertyProfile.is_active == True
            )
        ).scalars().all()
        property_codes = list(codes)
    
    if not property_codes:
        return None
    
    total_occupied_days = 0
    total_possible_days = len(property_codes) * total_days
    
    for code in property_codes:
        # 1. 예약된 날짜 계산
        reservations = db.execute(
            select(ReservationInfo).where(
                ReservationInfo.property_code == code,
                ReservationInfo.status.in_([
                    ReservationStatus.CONFIRMED.value,
                    ReservationStatus.ALTERATION_REQUESTED.value,
                    ReservationStatus.PENDING.value,
                ]),
                ReservationInfo.checkin_date <= end_date,
                ReservationInfo.checkout_date > start_date,
            )
        ).scalars().all()
        
        reserved_date_set = set()
        for res in reservations:
            if res.checkin_date and res.checkout_date:
                current = max(res.checkin_date, start_date)
                while current <= min(res.checkout_date - timedelta(days=1), end_date):
                    reserved_date_set.add(current)
                    current = current + timedelta(days=1)
        
        # 2. iCal 차단 날짜 (예약과 겹치지 않는 것만)
        blocked_dates = db.execute(
            select(IcalBlockedDate.blocked_date).where(
                IcalBlockedDate.property_code == code,
                IcalBlockedDate.blocked_date >= start_date,
                IcalBlockedDate.blocked_date <= end_date,
            )
        ).scalars().all()
        
        blocked_count = sum(1 for d in blocked_dates if d not in reserved_date_set)
        
        total_occupied_days += len(reserved_date_set) + blocked_count
    
    if total_possible_days == 0:
        return None
    
    return round(total_occupied_days / total_possible_days * 100, 1)


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/summary", response_model=AnalyticsSummaryDTO)
def get_analytics_summary(
    period: str = Query("today", description="today|week|month|custom"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    db: Session = Depends(get_db),
) -> AnalyticsSummaryDTO:
    """
    기간별 분석 요약.
    
    이전 동일 기간과 비교한 변화율 포함.
    """
    from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
    from app.domain.models.conversation import SendActionLog, SendAction, DraftReply, Conversation
    from app.domain.models.incoming_message import IncomingMessage, MessageDirection
    
    # 기간 계산
    start, end = get_date_range(period, start_date, end_date)
    prev_start, prev_end = get_previous_period(start, end)
    
    # datetime으로 변환 (UTC timezone aware)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
    prev_start_dt = datetime.combine(prev_start, datetime.min.time(), tzinfo=timezone.utc)
    prev_end_dt = datetime.combine(prev_end, datetime.max.time(), tzinfo=timezone.utc)
    
    # ========== 1. 예약 확정 건수 ==========
    # NOTE: created_at 기준 (RTB→confirmed 전환 시 created_at이 확정 시점으로 업데이트됨)
    reservation_conditions = [
        ReservationInfo.status == ReservationStatus.CONFIRMED.value,
        ReservationInfo.created_at >= start_dt,
        ReservationInfo.created_at <= end_dt,
    ]
    if property_code:
        reservation_conditions.append(ReservationInfo.property_code == property_code)
    
    reservations_confirmed = db.execute(
        select(func.count(ReservationInfo.id)).where(and_(*reservation_conditions))
    ).scalar() or 0
    
    # 이전 기간
    prev_reservation_conditions = [
        ReservationInfo.status == ReservationStatus.CONFIRMED.value,
        ReservationInfo.created_at >= prev_start_dt,
        ReservationInfo.created_at <= prev_end_dt,
    ]
    if property_code:
        prev_reservation_conditions.append(ReservationInfo.property_code == property_code)
    
    prev_reservations = db.execute(
        select(func.count(ReservationInfo.id)).where(and_(*prev_reservation_conditions))
    ).scalar() or 0
    
    # ========== 2. 메시지 발송 건수 ==========
    send_conditions = [
        SendActionLog.action == SendAction.send,
        SendActionLog.created_at >= start_dt,
        SendActionLog.created_at <= end_dt,
    ]
    if property_code:
        send_conditions.append(SendActionLog.property_code == property_code)
    
    messages_sent = db.execute(
        select(func.count(SendActionLog.id)).where(and_(*send_conditions))
    ).scalar() or 0
    
    # 이전 기간
    prev_send_conditions = [
        SendActionLog.action == SendAction.send,
        SendActionLog.created_at >= prev_start_dt,
        SendActionLog.created_at <= prev_end_dt,
    ]
    if property_code:
        prev_send_conditions.append(SendActionLog.property_code == property_code)
    
    prev_messages = db.execute(
        select(func.count(SendActionLog.id)).where(and_(*prev_send_conditions))
    ).scalar() or 0
    
    # ========== 3. 평균 응답 시간 ==========
    # Conversation.last_message_at (마지막 게스트 메시지) -> SendActionLog.created_at 시간 차이
    avg_response_minutes = None
    prev_avg_response = None
    
    try:
        # 현재 기간: 발송 시점 - 마지막 메시지 시점
        response_query = (
            select(
                func.avg(
                    extract('epoch', SendActionLog.created_at) - 
                    extract('epoch', Conversation.last_message_at)
                ) / 60  # 분 단위
            )
            .join(Conversation, SendActionLog.conversation_id == Conversation.id)
            .where(
                and_(
                    SendActionLog.action == SendAction.send,
                    SendActionLog.created_at >= start_dt,
                    SendActionLog.created_at <= end_dt,
                    Conversation.last_message_at.isnot(None),
                    # 음수 값 제외
                    SendActionLog.created_at > Conversation.last_message_at,
                    *(([SendActionLog.property_code == property_code] if property_code else []))
                )
            )
        )
        result = db.execute(response_query).scalar()
        logger.info(f"Avg response time query result: {result}")
        if result is not None and float(result) > 0:
            avg_response_minutes = round(float(result), 1)
        
        # 이전 기간
        prev_response_query = (
            select(
                func.avg(
                    extract('epoch', SendActionLog.created_at) - 
                    extract('epoch', Conversation.last_message_at)
                ) / 60
            )
            .join(Conversation, SendActionLog.conversation_id == Conversation.id)
            .where(
                and_(
                    SendActionLog.action == SendAction.send,
                    SendActionLog.created_at >= prev_start_dt,
                    SendActionLog.created_at <= prev_end_dt,
                    Conversation.last_message_at.isnot(None),
                    SendActionLog.created_at > Conversation.last_message_at,
                    *(([SendActionLog.property_code == property_code] if property_code else []))
                )
            )
        )
        prev_result = db.execute(prev_response_query).scalar()
        if prev_result is not None and float(prev_result) > 0:
            prev_avg_response = round(float(prev_result), 1)
    except Exception as e:
        logger.warning(f"Failed to calculate avg response time: {e}")
    
    # ========== 4. AI 채택률 ==========
    # 발송된 draft 중 수정 안 된 비율 (발송된 것만 대상)
    ai_adoption_rate = None
    prev_ai_adoption = None
    
    try:
        # 발송된 conversation_id 목록
        sent_conversation_ids = db.execute(
            select(SendActionLog.conversation_id).where(
                and_(
                    SendActionLog.action == SendAction.send,
                    SendActionLog.created_at >= start_dt,
                    SendActionLog.created_at <= end_dt,
                    *(([SendActionLog.property_code == property_code] if property_code else []))
                )
            )
        ).scalars().all()
        
        if sent_conversation_ids:
            # 발송된 draft 중 수정 안 된 것의 비율
            total_sent_drafts = db.execute(
                select(func.count(DraftReply.id)).where(
                    DraftReply.conversation_id.in_(sent_conversation_ids)
                )
            ).scalar() or 0
            
            unedited_sent_drafts = db.execute(
                select(func.count(DraftReply.id)).where(
                    and_(
                        DraftReply.conversation_id.in_(sent_conversation_ids),
                        DraftReply.is_edited == False
                    )
                )
            ).scalar() or 0
            
            if total_sent_drafts > 0:
                ai_adoption_rate = round(unedited_sent_drafts / total_sent_drafts * 100, 1)
        
        # 이전 기간
        prev_sent_conversation_ids = db.execute(
            select(SendActionLog.conversation_id).where(
                and_(
                    SendActionLog.action == SendAction.send,
                    SendActionLog.created_at >= prev_start_dt,
                    SendActionLog.created_at <= prev_end_dt,
                    *(([SendActionLog.property_code == property_code] if property_code else []))
                )
            )
        ).scalars().all()
        
        if prev_sent_conversation_ids:
            prev_total_sent = db.execute(
                select(func.count(DraftReply.id)).where(
                    DraftReply.conversation_id.in_(prev_sent_conversation_ids)
                )
            ).scalar() or 0
            
            prev_unedited_sent = db.execute(
                select(func.count(DraftReply.id)).where(
                    and_(
                        DraftReply.conversation_id.in_(prev_sent_conversation_ids),
                        DraftReply.is_edited == False
                    )
                )
            ).scalar() or 0
            
            if prev_total_sent > 0:
                prev_ai_adoption = round(prev_unedited_sent / prev_total_sent * 100, 1)
    except Exception as e:
        logger.warning(f"Failed to calculate AI adoption rate: {e}")
    
    # ========== 5. 예약 리드타임 ==========
    # NOTE: 예약 확정일(created_at) 기준으로 체크인까지의 일수
    # RTB→confirmed 전환 시 created_at이 확정 시점으로 업데이트됨
    lead_time_days = None
    
    try:
        lead_time_query = (
            select(
                func.avg(
                    extract('epoch', ReservationInfo.checkin_date) - 
                    extract('epoch', func.date(ReservationInfo.created_at))
                ) / 86400  # 일 단위
            )
            .where(
                and_(
                    ReservationInfo.status == ReservationStatus.CONFIRMED.value,
                    ReservationInfo.created_at >= start_dt,
                    ReservationInfo.created_at <= end_dt,
                    ReservationInfo.checkin_date.isnot(None),
                    *(([ReservationInfo.property_code == property_code] if property_code else []))
                )
            )
        )
        result = db.execute(lead_time_query).scalar()
        if result and result > 0:
            lead_time_days = round(float(result), 1)
    except Exception as e:
        logger.warning(f"Failed to calculate lead time: {e}")
    
    # ========== 6. ADR (Average Daily Rate) ==========
    # NOTE: host_payout / nights (호스트 수익 기준)
    adr = None
    
    try:
        adr_query = (
            select(
                func.sum(ReservationInfo.host_payout),
                func.sum(ReservationInfo.nights)
            )
            .where(
                and_(
                    ReservationInfo.status == ReservationStatus.CONFIRMED.value,
                    ReservationInfo.created_at >= start_dt,
                    ReservationInfo.created_at <= end_dt,
                    ReservationInfo.host_payout.isnot(None),
                    ReservationInfo.nights.isnot(None),
                    ReservationInfo.nights > 0,
                    *(([ReservationInfo.property_code == property_code] if property_code else []))
                )
            )
        )
        total_payout, total_nights = db.execute(adr_query).one()
        if total_payout and total_nights and total_nights > 0:
            adr = int(total_payout / total_nights)
    except Exception as e:
        logger.warning(f"Failed to calculate ADR: {e}")
    
    # ========== 7. 점유율 ==========
    occupancy_rate = calc_occupancy_rate(db, start, end, property_code)
    
    return AnalyticsSummaryDTO(
        period=period,
        start_date=start,
        end_date=end,
        
        reservations_confirmed=reservations_confirmed,
        messages_sent=messages_sent,
        avg_response_minutes=avg_response_minutes,
        ai_adoption_rate=ai_adoption_rate,
        
        lead_time_days=lead_time_days,
        adr=adr,
        occupancy_rate=occupancy_rate,
        
        reservations_confirmed_change=calc_change(reservations_confirmed, prev_reservations),
        messages_sent_change=calc_change(messages_sent, prev_messages),
        avg_response_change=calc_diff(avg_response_minutes, prev_avg_response),
        ai_adoption_change=calc_diff(ai_adoption_rate, prev_ai_adoption),
    )


@router.get("/trend", response_model=TrendResponse)
def get_analytics_trend(
    months: int = Query(6, ge=1, le=12, description="최근 N개월"),
    property_code: Optional[str] = Query(None, description="특정 숙소 필터"),
    db: Session = Depends(get_db),
) -> TrendResponse:
    """
    월별 트렌드 데이터.
    
    NOTE: 기간 선택(period)과 무관하게 최근 N개월 전체 데이터 조회
    """
    from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
    from app.domain.models.conversation import SendActionLog, SendAction, DraftReply
    
    items = []
    today = date.today()
    
    for i in range(months):
        # 해당 월의 시작/끝 계산 (간소화)
        # i=0: 이번 달, i=1: 저번 달, ...
        year = today.year
        month = today.month - i
        
        while month <= 0:
            month += 12
            year -= 1
        
        month_start = date(year, month, 1)
        
        # 월 마지막 날 계산
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        # 이번 달이면 오늘까지만
        if i == 0:
            month_end = today
        
        month_str = month_start.strftime("%Y-%m")
        
        start_dt = datetime.combine(month_start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(month_end, datetime.max.time(), tzinfo=timezone.utc)
        
        # 예약 확정 (created_at 기준)
        reservation_conditions = [
            ReservationInfo.status == ReservationStatus.CONFIRMED.value,
            ReservationInfo.created_at >= start_dt,
            ReservationInfo.created_at <= end_dt,
        ]
        if property_code:
            reservation_conditions.append(ReservationInfo.property_code == property_code)
        
        reservations = db.execute(
            select(func.count(ReservationInfo.id)).where(and_(*reservation_conditions))
        ).scalar() or 0
        
        # 메시지 발송
        send_conditions = [
            SendActionLog.action == SendAction.send,
            SendActionLog.created_at >= start_dt,
            SendActionLog.created_at <= end_dt,
        ]
        if property_code:
            send_conditions.append(SendActionLog.property_code == property_code)
        
        messages = db.execute(
            select(func.count(SendActionLog.id)).where(and_(*send_conditions))
        ).scalar() or 0
        
        # AI 채택률 (발송된 것만 대상)
        ai_rate = None
        sent_conv_ids = db.execute(
            select(SendActionLog.conversation_id).where(and_(*send_conditions))
        ).scalars().all()
        
        if sent_conv_ids:
            total_sent_drafts = db.execute(
                select(func.count(DraftReply.id)).where(
                    DraftReply.conversation_id.in_(sent_conv_ids)
                )
            ).scalar() or 0
            
            if total_sent_drafts > 0:
                unedited = db.execute(
                    select(func.count(DraftReply.id)).where(
                        and_(
                            DraftReply.conversation_id.in_(sent_conv_ids),
                            DraftReply.is_edited == False
                        )
                    )
                ).scalar() or 0
                ai_rate = round(unedited / total_sent_drafts * 100, 1)
        
        # ADR (host_payout 기준, created_at 기준)
        adr = None
        adr_query = (
            select(
                func.sum(ReservationInfo.host_payout),
                func.sum(ReservationInfo.nights)
            )
            .where(
                and_(
                    ReservationInfo.status == ReservationStatus.CONFIRMED.value,
                    ReservationInfo.created_at >= start_dt,
                    ReservationInfo.created_at <= end_dt,
                    ReservationInfo.host_payout.isnot(None),
                    ReservationInfo.nights.isnot(None),
                    ReservationInfo.nights > 0,
                    *(([ReservationInfo.property_code == property_code] if property_code else []))
                )
            )
        )
        try:
            total_payout, total_nights = db.execute(adr_query).one()
            if total_payout and total_nights and total_nights > 0:
                adr = int(total_payout / total_nights)
        except:
            pass
        
        # 리드타임 (created_at 기준)
        lead_time = None
        try:
            lead_query = (
                select(
                    func.avg(
                        extract('epoch', ReservationInfo.checkin_date) - 
                        extract('epoch', func.date(ReservationInfo.created_at))
                    ) / 86400
                )
                .where(
                    and_(
                        ReservationInfo.status == ReservationStatus.CONFIRMED.value,
                        ReservationInfo.created_at >= start_dt,
                        ReservationInfo.created_at <= end_dt,
                        ReservationInfo.checkin_date.isnot(None),
                        *(([ReservationInfo.property_code == property_code] if property_code else []))
                    )
                )
            )
            result = db.execute(lead_query).scalar()
            if result and result > 0:
                lead_time = round(float(result), 1)
        except:
            pass
        
        items.append(TrendItemDTO(
            month=month_str,
            reservations_confirmed=reservations,
            messages_sent=messages,
            avg_response_minutes=None,  # 월별로는 복잡해서 생략
            ai_adoption_rate=ai_rate,
            lead_time_days=lead_time,
            adr=adr,
            occupancy_rate=calc_occupancy_rate(db, month_start, month_end, property_code),
        ))
    
    # 오래된 순으로 정렬
    items.reverse()
    
    return TrendResponse(items=items)


@router.get("/by-property", response_model=PropertyComparisonResponse)
def get_analytics_by_property(
    period: str = Query("month", description="today|week|month|custom"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> PropertyComparisonResponse:
    """
    숙소별 비교 데이터.
    """
    from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
    from app.domain.models.conversation import SendActionLog, SendAction, DraftReply
    from app.domain.models.property_profile import PropertyProfile
    
    start, end = get_date_range(period, start_date, end_date)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
    
    # 모든 property_code 가져오기
    property_codes = db.execute(
        select(PropertyProfile.property_code, PropertyProfile.name)
    ).all()
    
    items = []
    
    for code, name in property_codes:
        # 예약 확정 (created_at 기준)
        reservations = db.execute(
            select(func.count(ReservationInfo.id)).where(
                and_(
                    ReservationInfo.status == ReservationStatus.CONFIRMED.value,
                    ReservationInfo.created_at >= start_dt,
                    ReservationInfo.created_at <= end_dt,
                    ReservationInfo.property_code == code,
                )
            )
        ).scalar() or 0
        
        # 메시지 발송
        messages = db.execute(
            select(func.count(SendActionLog.id)).where(
                and_(
                    SendActionLog.action == SendAction.send,
                    SendActionLog.created_at >= start_dt,
                    SendActionLog.created_at <= end_dt,
                    SendActionLog.property_code == code,
                )
            )
        ).scalar() or 0
        
        # ADR (host_payout 기준, created_at 기준)
        adr = None
        try:
            total_payout, total_nights = db.execute(
                select(
                    func.sum(ReservationInfo.host_payout),
                    func.sum(ReservationInfo.nights)
                ).where(
                    and_(
                        ReservationInfo.status == ReservationStatus.CONFIRMED.value,
                        ReservationInfo.created_at >= start_dt,
                        ReservationInfo.created_at <= end_dt,
                        ReservationInfo.property_code == code,
                        ReservationInfo.host_payout.isnot(None),
                        ReservationInfo.nights.isnot(None),
                        ReservationInfo.nights > 0,
                    )
                )
            ).one()
            if total_payout and total_nights and total_nights > 0:
                adr = int(total_payout / total_nights)
        except:
            pass
        
        # 리드타임 계산 (created_at 기준)
        lead_time = None
        try:
            lead_query = (
                select(
                    func.avg(
                        extract('epoch', ReservationInfo.checkin_date) - 
                        extract('epoch', func.date(ReservationInfo.created_at))
                    ) / 86400  # 일 단위
                )
                .where(
                    and_(
                        ReservationInfo.status == ReservationStatus.CONFIRMED.value,
                        ReservationInfo.created_at >= start_dt,
                        ReservationInfo.created_at <= end_dt,
                        ReservationInfo.property_code == code,
                        ReservationInfo.checkin_date.isnot(None),
                    )
                )
            )
            result = db.execute(lead_query).scalar()
            if result and result > 0:
                lead_time = round(float(result), 1)
        except:
            pass
        
        # 데이터가 하나라도 있는 경우만 추가
        if reservations > 0 or messages > 0:
            items.append(PropertyComparisonDTO(
                property_code=code,
                property_name=name,
                reservations_confirmed=reservations,
                messages_sent=messages,
                avg_response_minutes=None,
                ai_adoption_rate=None,
                lead_time_days=lead_time,
                adr=adr,
                occupancy_rate=calc_occupancy_rate(db, start, end, code),
            ))
    
    # 예약 건수 기준 정렬
    items.sort(key=lambda x: x.reservations_confirmed, reverse=True)
    
    return PropertyComparisonResponse(items=items)


# =============================================================================
# OC (Operational Commitment) Analytics
# =============================================================================

class OCTopicCountDTO(BaseModel):
    """Topic별 OC 건수"""
    topic: str
    topic_label: str
    count: int
    percentage: float


class OCStatusCountDTO(BaseModel):
    """Status별 OC 건수"""
    status: str
    status_label: str
    count: int


class OCTrendItemDTO(BaseModel):
    """월별 OC 트렌드"""
    month: str
    total_count: int
    completed_count: int  # done + resolved
    by_topic: List[OCTopicCountDTO]


class OCByPropertyDTO(BaseModel):
    """숙소별 OC 발생"""
    property_code: str
    property_name: Optional[str]
    total_count: int
    by_topic: List[OCTopicCountDTO]


class OCSummaryDTO(BaseModel):
    """OC 요약 통계"""
    period: str
    start_date: date
    end_date: date
    
    # 기본 지표
    total_count: int
    completed_count: int  # done + resolved
    completion_rate: Optional[float]  # 완료율 (%)
    
    # 이전 기간 대비
    total_count_change: Optional[float]
    
    # 분포
    by_topic: List[OCTopicCountDTO]
    by_status: List[OCStatusCountDTO]


class OCTrendResponse(BaseModel):
    """OC 월별 트렌드 응답"""
    items: List[OCTrendItemDTO]


class OCByPropertyResponse(BaseModel):
    """OC 숙소별 분포 응답"""
    items: List[OCByPropertyDTO]


# Topic 라벨 매핑
OC_TOPIC_LABELS = {
    "early_checkin": "얼리 체크인",
    "late_checkout": "레이트 체크아웃",
    "checkin_time": "체크인 시간",
    "checkout_time": "체크아웃 시간",
    "guest_count_change": "인원 변경",
    "reservation_change": "예약 변경",
    "free_provision": "무료 제공",
    "extra_fee": "추가 요금",
    "amenity_request": "어메니티 요청",
    "amenity_prep": "어메니티 준비",
    "pet_policy": "반려동물",
    "issue_resolution": "문제 해결",      # 🆕 추가
    "follow_up": "확인 후 연락",
    "visit_schedule": "방문 일정",
    "refund": "환불",
    "refund_process": "환불 처리",        # 🆕 추가
    "refund_check": "환불 확인",          # 기존 호환
    "payment": "결제",
    "payment_process": "결제 처리",       # 🆕 추가
    "compensation": "보상",
    "special_request": "특별 요청",
    "other": "기타",
    # 기존 호환 (마이그레이션 전)
    "facility_issue": "시설 문제",
}

OC_STATUS_LABELS = {
    "pending": "대기 중",
    "done": "완료",
    "resolved": "해소됨",
    "suggested_resolve": "해소 제안",
}


@router.get("/oc/summary", response_model=OCSummaryDTO)
def get_oc_summary(
    period: str = Query("month", description="today|week|month|custom"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    property_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> OCSummaryDTO:
    """
    OC 요약 통계
    
    - 총 발생 건수
    - 완료율 (done + resolved / total)
    - Topic별 분포
    - Status별 분포
    """
    from app.domain.models.operational_commitment import OperationalCommitment, OCStatus
    from app.domain.models.conversation import Conversation
    
    start, end = get_date_range(period, start_date, end_date)
    prev_start, prev_end = get_previous_period(start, end)
    
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
    prev_start_dt = datetime.combine(prev_start, datetime.min.time(), tzinfo=timezone.utc)
    prev_end_dt = datetime.combine(prev_end, datetime.max.time(), tzinfo=timezone.utc)
    
    # 기본 쿼리 조건
    base_conditions = [
        OperationalCommitment.created_at >= start_dt,
        OperationalCommitment.created_at <= end_dt,
    ]
    
    # property_code 필터
    if property_code:
        subq = select(Conversation.id).where(Conversation.property_code == property_code)
        base_conditions.append(OperationalCommitment.conversation_id.in_(subq))
    
    # 총 건수
    total_count = db.execute(
        select(func.count(OperationalCommitment.id)).where(and_(*base_conditions))
    ).scalar() or 0
    
    # 완료 건수 (done + resolved)
    completed_count = db.execute(
        select(func.count(OperationalCommitment.id)).where(
            and_(
                *base_conditions,
                OperationalCommitment.status.in_([
                    OCStatus.done.value,
                    OCStatus.resolved.value,
                ])
            )
        )
    ).scalar() or 0
    
    # 완료율
    completion_rate = None
    if total_count > 0:
        completion_rate = round(completed_count / total_count * 100, 1)
    
    # 이전 기간 총 건수
    prev_conditions = [
        OperationalCommitment.created_at >= prev_start_dt,
        OperationalCommitment.created_at <= prev_end_dt,
    ]
    if property_code:
        prev_conditions.append(OperationalCommitment.conversation_id.in_(subq))
    
    prev_total = db.execute(
        select(func.count(OperationalCommitment.id)).where(and_(*prev_conditions))
    ).scalar() or 0
    
    total_count_change = calc_change(total_count, prev_total)
    
    # Topic별 분포
    topic_counts = db.execute(
        select(
            OperationalCommitment.topic,
            func.count(OperationalCommitment.id).label("count")
        )
        .where(and_(*base_conditions))
        .group_by(OperationalCommitment.topic)
        .order_by(func.count(OperationalCommitment.id).desc())
    ).all()
    
    by_topic = []
    for topic, count in topic_counts:
        by_topic.append(OCTopicCountDTO(
            topic=topic,
            topic_label=OC_TOPIC_LABELS.get(topic, topic),
            count=count,
            percentage=round(count / total_count * 100, 1) if total_count > 0 else 0,
        ))
    
    # Status별 분포 (전체 OC 기준 - 기간 필터 없음)
    # "현재 OC 현황"을 보여주기 위함
    all_status_conditions = []
    if property_code:
        subq = select(Conversation.id).where(Conversation.property_code == property_code)
        all_status_conditions.append(OperationalCommitment.conversation_id.in_(subq))
    
    if all_status_conditions:
        status_counts = db.execute(
            select(
                OperationalCommitment.status,
                func.count(OperationalCommitment.id).label("count")
            )
            .where(and_(*all_status_conditions))
            .group_by(OperationalCommitment.status)
        ).all()
    else:
        status_counts = db.execute(
            select(
                OperationalCommitment.status,
                func.count(OperationalCommitment.id).label("count")
            )
            .group_by(OperationalCommitment.status)
        ).all()
    
    by_status = []
    for status, count in status_counts:
        by_status.append(OCStatusCountDTO(
            status=status,
            status_label=OC_STATUS_LABELS.get(status, status),
            count=count,
        ))
    
    return OCSummaryDTO(
        period=period,
        start_date=start,
        end_date=end,
        total_count=total_count,
        completed_count=completed_count,
        completion_rate=completion_rate,
        total_count_change=total_count_change,
        by_topic=by_topic,
        by_status=by_status,
    )


@router.get("/oc/trend", response_model=OCTrendResponse)
def get_oc_trend(
    months: int = Query(6, ge=1, le=12),
    property_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> OCTrendResponse:
    """
    OC 월별 트렌드
    
    NOTE: 기간 선택(period)과 무관하게 최근 N개월 전체 데이터 조회
    """
    from app.domain.models.operational_commitment import OperationalCommitment
    from app.domain.models.conversation import Conversation
    
    today = date.today()
    items = []
    
    # property_code 필터용 서브쿼리
    subq = None
    if property_code:
        subq = select(Conversation.id).where(Conversation.property_code == property_code)
    
    for i in range(months):
        # 해당 월의 시작/끝 계산 (간소화)
        year = today.year
        month = today.month - i
        
        while month <= 0:
            month += 12
            year -= 1
        
        month_start = date(year, month, 1)
        
        # 월 마지막 날 계산
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        # 이번 달이면 오늘까지만
        if i == 0:
            month_end = today
        
        month_str = month_start.strftime("%Y-%m")
        
        start_dt = datetime.combine(month_start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(month_end, datetime.max.time(), tzinfo=timezone.utc)
        
        # 기본 조건
        conditions = [
            OperationalCommitment.created_at >= start_dt,
            OperationalCommitment.created_at <= end_dt,
        ]
        if subq is not None:
            conditions.append(OperationalCommitment.conversation_id.in_(subq))
        
        # 총 건수
        total_count = db.execute(
            select(func.count(OperationalCommitment.id)).where(and_(*conditions))
        ).scalar() or 0
        
        # 완료 건수 (done + resolved)
        from app.domain.models.operational_commitment import OCStatus
        completed_count = db.execute(
            select(func.count(OperationalCommitment.id)).where(
                and_(
                    *conditions,
                    OperationalCommitment.status.in_([
                        OCStatus.done.value,
                        OCStatus.resolved.value,
                    ])
                )
            )
        ).scalar() or 0
        
        # Topic별 분포
        topic_counts = db.execute(
            select(
                OperationalCommitment.topic,
                func.count(OperationalCommitment.id).label("count")
            )
            .where(and_(*conditions))
            .group_by(OperationalCommitment.topic)
            .order_by(func.count(OperationalCommitment.id).desc())
        ).all()
        
        by_topic = []
        for topic, count in topic_counts:
            by_topic.append(OCTopicCountDTO(
                topic=topic,
                topic_label=OC_TOPIC_LABELS.get(topic, topic),
                count=count,
                percentage=round(count / total_count * 100, 1) if total_count > 0 else 0,
            ))
        
        items.append(OCTrendItemDTO(
            month=month_str,
            total_count=total_count,
            completed_count=completed_count,
            by_topic=by_topic,
        ))
    
    # 오래된 순으로 정렬
    items.reverse()
    
    return OCTrendResponse(items=items)


@router.get("/oc/by-property", response_model=OCByPropertyResponse)
def get_oc_by_property(
    period: str = Query("month", description="today|week|month|custom"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
) -> OCByPropertyResponse:
    """
    숙소별 OC 발생 현황
    
    - 숙소별 총 건수
    - 숙소별 Topic 분포
    """
    from app.domain.models.operational_commitment import OperationalCommitment
    from app.domain.models.conversation import Conversation
    from app.domain.models.property_profile import PropertyProfile
    
    start, end = get_date_range(period, start_date, end_date)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
    
    # 모든 property 가져오기
    properties = db.execute(
        select(PropertyProfile.property_code, PropertyProfile.name)
    ).all()
    
    items = []
    
    for code, name in properties:
        # 해당 property의 conversation_id 목록
        conv_ids = db.execute(
            select(Conversation.id).where(Conversation.property_code == code)
        ).scalars().all()
        
        if not conv_ids:
            continue
        
        # 조건
        conditions = [
            OperationalCommitment.created_at >= start_dt,
            OperationalCommitment.created_at <= end_dt,
            OperationalCommitment.conversation_id.in_(conv_ids),
        ]
        
        # 총 건수
        total_count = db.execute(
            select(func.count(OperationalCommitment.id)).where(and_(*conditions))
        ).scalar() or 0
        
        if total_count == 0:
            continue
        
        # Topic별 분포
        topic_counts = db.execute(
            select(
                OperationalCommitment.topic,
                func.count(OperationalCommitment.id).label("count")
            )
            .where(and_(*conditions))
            .group_by(OperationalCommitment.topic)
            .order_by(func.count(OperationalCommitment.id).desc())
        ).all()
        
        by_topic = []
        for topic, count in topic_counts:
            by_topic.append(OCTopicCountDTO(
                topic=topic,
                topic_label=OC_TOPIC_LABELS.get(topic, topic),
                count=count,
                percentage=round(count / total_count * 100, 1) if total_count > 0 else 0,
            ))
        
        items.append(OCByPropertyDTO(
            property_code=code,
            property_name=name,
            total_count=total_count,
            by_topic=by_topic,
        ))
    
    # OC 건수 기준 내림차순 정렬
    items.sort(key=lambda x: x.total_count, reverse=True)
    
    return OCByPropertyResponse(items=items)


# =============================================================================
# OC 히트맵 (숙소별 x 토픽별 매트릭스)
# =============================================================================

class OCHeatmapCellDTO(BaseModel):
    """히트맵 셀 (숙소-토픽 조합)"""
    topic: str
    topic_label: str
    count: int


class OCHeatmapRowDTO(BaseModel):
    """히트맵 행 (숙소별)"""
    property_code: str
    property_name: Optional[str]
    total_count: int
    cells: List[OCHeatmapCellDTO]


class OCHeatmapResponse(BaseModel):
    """OC 히트맵 응답"""
    topics: List[str]  # 컬럼 헤더용 토픽 목록
    topic_labels: Dict[str, str]  # topic -> label 매핑
    rows: List[OCHeatmapRowDTO]


@router.get("/oc/heatmap", response_model=OCHeatmapResponse)
def get_oc_heatmap(
    db: Session = Depends(get_db),
) -> OCHeatmapResponse:
    """
    숙소별 x 토픽별 OC 히트맵 데이터
    
    전체 기간 기준으로 숙소별로 어떤 유형의 문제가 많이 발생하는지 파악
    """
    from app.domain.models.operational_commitment import OperationalCommitment
    from app.domain.models.conversation import Conversation
    from app.domain.models.property_profile import PropertyProfile
    
    # 전체 토픽 목록 (DB에 있는 것만)
    all_topics = db.execute(
        select(OperationalCommitment.topic)
        .distinct()
        .order_by(OperationalCommitment.topic)
    ).scalars().all()
    
    # 모든 property 가져오기
    properties = db.execute(
        select(PropertyProfile.property_code, PropertyProfile.name)
    ).all()
    
    rows = []
    
    for code, name in properties:
        # 해당 property의 conversation_id 목록
        conv_ids = db.execute(
            select(Conversation.id).where(Conversation.property_code == code)
        ).scalars().all()
        
        if not conv_ids:
            continue
        
        # 숙소별 전체 OC 건수
        total_count = db.execute(
            select(func.count(OperationalCommitment.id)).where(
                OperationalCommitment.conversation_id.in_(conv_ids)
            )
        ).scalar() or 0
        
        if total_count == 0:
            continue
        
        # 토픽별 건수
        topic_counts = db.execute(
            select(
                OperationalCommitment.topic,
                func.count(OperationalCommitment.id).label("count")
            )
            .where(OperationalCommitment.conversation_id.in_(conv_ids))
            .group_by(OperationalCommitment.topic)
        ).all()
        
        topic_count_map = {topic: count for topic, count in topic_counts}
        
        # 모든 토픽에 대해 셀 생성 (없으면 0)
        cells = []
        for topic in all_topics:
            cells.append(OCHeatmapCellDTO(
                topic=topic,
                topic_label=OC_TOPIC_LABELS.get(topic, topic),
                count=topic_count_map.get(topic, 0),
            ))
        
        rows.append(OCHeatmapRowDTO(
            property_code=code,
            property_name=name,
            total_count=total_count,
            cells=cells,
        ))
    
    # 총 건수 기준 내림차순 정렬
    rows.sort(key=lambda x: x.total_count, reverse=True)
    
    return OCHeatmapResponse(
        topics=list(all_topics),
        topic_labels=OC_TOPIC_LABELS,
        rows=rows,
    )


# =============================================================================
# OC 상세 목록 (숙소 + 토픽별 드릴다운)
# =============================================================================

class OCDetailItemDTO(BaseModel):
    """OC 상세 항목"""
    oc_id: str
    conversation_id: str
    description: str
    evidence_quote: Optional[str]
    status: str
    status_label: str
    target_date: Optional[date]
    created_at: datetime
    guest_name: Optional[str]
    checkin_date: Optional[date]
    checkout_date: Optional[date]


class OCDetailListResponse(BaseModel):
    """OC 상세 목록 응답"""
    property_code: str
    property_name: Optional[str]
    topic: str
    topic_label: str
    total_count: int
    items: List[OCDetailItemDTO]


@router.get("/oc/detail/{property_code}/{topic}", response_model=OCDetailListResponse)
def get_oc_detail_list(
    property_code: str,
    topic: str,
    db: Session = Depends(get_db),
) -> OCDetailListResponse:
    """
    특정 숙소 + 토픽의 OC 상세 목록
    
    히트맵에서 클릭 시 실제 어떤 문제들이 발생했는지 확인
    """
    from app.domain.models.operational_commitment import OperationalCommitment
    from app.domain.models.conversation import Conversation
    from app.domain.models.property_profile import PropertyProfile
    from app.domain.models.reservation_info import ReservationInfo
    
    # Property 정보
    prop = db.execute(
        select(PropertyProfile.name).where(PropertyProfile.property_code == property_code)
    ).scalar()
    
    # 해당 property의 conversation_id 목록
    conv_ids = db.execute(
        select(Conversation.id).where(Conversation.property_code == property_code)
    ).scalars().all()
    
    if not conv_ids:
        return OCDetailListResponse(
            property_code=property_code,
            property_name=prop,
            topic=topic,
            topic_label=OC_TOPIC_LABELS.get(topic, topic),
            total_count=0,
            items=[],
        )
    
    # OC 목록 조회
    ocs = db.execute(
        select(OperationalCommitment)
        .where(
            and_(
                OperationalCommitment.conversation_id.in_(conv_ids),
                OperationalCommitment.topic == topic,
            )
        )
        .order_by(OperationalCommitment.created_at.desc())
    ).scalars().all()
    
    items = []
    for oc in ocs:
        guest_name = None
        checkin_date = None
        checkout_date = None
        
        # OC의 provenance_message_id를 통해 IncomingMessage에서 정보 가져오기
        if oc.provenance_message_id:
            from app.domain.models.incoming_message import IncomingMessage
            msg = db.execute(
                select(IncomingMessage).where(IncomingMessage.id == oc.provenance_message_id)
            ).scalar()
            if msg:
                guest_name = msg.guest_name
                checkin_date = msg.checkin_date
                checkout_date = msg.checkout_date
        
        items.append(OCDetailItemDTO(
            oc_id=str(oc.id),
            conversation_id=str(oc.conversation_id),
            description=oc.description,
            evidence_quote=oc.evidence_quote,
            status=oc.status,
            status_label=OC_STATUS_LABELS.get(oc.status, oc.status),
            target_date=oc.target_date,
            created_at=oc.created_at,
            guest_name=guest_name,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
        ))
    
    return OCDetailListResponse(
        property_code=property_code,
        property_name=prop,
        topic=topic,
        topic_label=OC_TOPIC_LABELS.get(topic, topic),
        total_count=len(items),
        items=items,
    )
