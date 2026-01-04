"""
Calendar API

숙소별 달력 데이터, 점유율, iCal 동기화, 예약 가능 여부 체크
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Literal
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
from app.domain.models.ical_blocked_date import IcalBlockedDate
from app.domain.models.property_profile import PropertyProfile
from app.services.ical_service import IcalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["Calendar"])


# ========== DTOs ==========

class CalendarDayType(str, Enum):
    """달력 날짜 타입"""
    AVAILABLE = "available"      # 예약 가능
    RESERVED = "reserved"        # 예약됨
    BLOCKED = "blocked"          # 차단됨 (iCal)
    CHECKIN = "checkin"          # 체크인 날
    CHECKOUT = "checkout"        # 체크아웃 날


class CalendarDayDTO(BaseModel):
    """달력 하루 데이터"""
    date: date
    type: CalendarDayType
    guest_name: Optional[str] = None
    reservation_code: Optional[str] = None
    summary: Optional[str] = None  # iCal 차단 사유


class CalendarMonthDTO(BaseModel):
    """월별 달력 데이터"""
    property_code: str
    property_name: str
    year: int
    month: int
    days: list[CalendarDayDTO]
    occupancy_rate: float  # 점유율 (0~100)
    reserved_days: int
    blocked_days: int
    available_days: int
    total_days: int


class OccupancyDTO(BaseModel):
    """점유율 데이터"""
    property_code: str
    property_name: str
    period_start: date
    period_end: date
    occupancy_rate: float  # 0~100
    reserved_days: int
    blocked_days: int
    available_days: int
    total_days: int


class IcalSyncResultDTO(BaseModel):
    """iCal 동기화 결과"""
    property_code: str
    synced_dates: int
    last_synced_at: datetime


class IcalUrlUpdateRequest(BaseModel):
    """iCal URL 업데이트 요청"""
    ical_url: str


class AvailabilityCheckRequest(BaseModel):
    """예약 가능 여부 체크 요청"""
    property_code: str
    checkin_date: date
    checkout_date: date


class ConflictDTO(BaseModel):
    """충돌 정보"""
    date: date
    type: Literal["reservation", "blocked"]
    guest_name: Optional[str] = None
    summary: Optional[str] = None


class AvailabilityCheckResponse(BaseModel):
    """예약 가능 여부 체크 응답"""
    available: bool
    conflicts: list[ConflictDTO]
    message: str


# ========== Helper Functions ==========

def _get_month_range(year: int, month: int) -> tuple[date, date]:
    """월의 시작일과 종료일(다음달 1일) 반환"""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _get_days_in_month(year: int, month: int) -> int:
    """해당 월의 일수"""
    start, end = _get_month_range(year, month)
    return (end - start).days


# ========== Endpoints ==========

@router.get("/{property_code}", response_model=CalendarMonthDTO)
def get_calendar(
    property_code: str,
    year: int = Query(default=None, description="조회 연도 (기본: 현재)"),
    month: int = Query(default=None, ge=1, le=12, description="조회 월 (1-12)"),
    db: Session = Depends(get_db),
) -> CalendarMonthDTO:
    """
    숙소별 월간 달력 데이터 조회
    
    - 예약 정보 (reservation_info)
    - 차단 날짜 (ical_blocked_dates)
    - 점유율
    """
    # 기본값: 현재 월
    today = date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    
    # Property 확인
    profile = db.execute(
        select(PropertyProfile).where(
            PropertyProfile.property_code == property_code,
            PropertyProfile.is_active == True,
        )
    ).scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_code}")
    
    # 월 범위
    start_date, end_date = _get_month_range(year, month)
    total_days = (end_date - start_date).days
    
    # 1. 예약 정보 조회 (해당 월과 겹치는 모든 예약)
    reservations = db.execute(
        select(ReservationInfo).where(
            ReservationInfo.property_code == property_code,
            ReservationInfo.status.in_([
                ReservationStatus.CONFIRMED.value,
                ReservationStatus.ALTERATION_REQUESTED.value,
                ReservationStatus.PENDING.value,
            ]),
            ReservationInfo.checkin_date < end_date,
            ReservationInfo.checkout_date > start_date,
        )
    ).scalars().all()
    
    # 2. 차단 날짜 조회
    blocked_dates = db.execute(
        select(IcalBlockedDate).where(
            IcalBlockedDate.property_code == property_code,
            IcalBlockedDate.blocked_date >= start_date,
            IcalBlockedDate.blocked_date < end_date,
        )
    ).scalars().all()
    
    # 날짜별 데이터 생성
    blocked_set = {bd.blocked_date: bd for bd in blocked_dates}
    days: list[CalendarDayDTO] = []
    reserved_count = 0
    blocked_count = 0
    
    current = start_date
    while current < end_date:
        day_type = CalendarDayType.AVAILABLE
        guest_name = None
        reservation_code = None
        summary = None
        
        # 예약 체크
        for res in reservations:
            if res.checkin_date and res.checkout_date:
                if res.checkin_date <= current < res.checkout_date:
                    if current == res.checkin_date:
                        day_type = CalendarDayType.CHECKIN
                    else:
                        day_type = CalendarDayType.RESERVED
                    guest_name = res.guest_name
                    reservation_code = res.reservation_code
                    reserved_count += 1
                    break
        
        # 예약이 없으면 차단 체크
        if day_type == CalendarDayType.AVAILABLE and current in blocked_set:
            day_type = CalendarDayType.BLOCKED
            summary = blocked_set[current].summary
            blocked_count += 1
        
        days.append(CalendarDayDTO(
            date=current,
            type=day_type,
            guest_name=guest_name,
            reservation_code=reservation_code,
            summary=summary,
        ))
        
        current += timedelta(days=1)
    
    # 점유율 계산
    occupied_days = reserved_count + blocked_count
    available_days = total_days - occupied_days
    occupancy_rate = (occupied_days / total_days * 100) if total_days > 0 else 0
    
    return CalendarMonthDTO(
        property_code=property_code,
        property_name=profile.name,
        year=year,
        month=month,
        days=days,
        occupancy_rate=round(occupancy_rate, 1),
        reserved_days=reserved_count,
        blocked_days=blocked_count,
        available_days=available_days,
        total_days=total_days,
    )


@router.get("/{property_code}/occupancy", response_model=OccupancyDTO)
def get_occupancy(
    property_code: str,
    start: date = Query(default=None, description="시작일 (기본: 이번 달 1일)"),
    end: date = Query(default=None, description="종료일 (기본: 이번 달 말일)"),
    db: Session = Depends(get_db),
) -> OccupancyDTO:
    """
    숙소별 점유율 조회
    
    지정 기간 내 (예약일 + 차단일) / 전체일 × 100
    """
    # 기본값: 이번 달
    today = date.today()
    if start is None:
        start = date(today.year, today.month, 1)
    if end is None:
        start_date, end = _get_month_range(today.year, today.month)
    
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be after start")
    
    # Property 확인
    profile = db.execute(
        select(PropertyProfile).where(
            PropertyProfile.property_code == property_code,
            PropertyProfile.is_active == True,
        )
    ).scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_code}")
    
    total_days = (end - start).days
    
    # 예약된 날짜 수 계산
    reservations = db.execute(
        select(ReservationInfo).where(
            ReservationInfo.property_code == property_code,
            ReservationInfo.status.in_([
                ReservationStatus.CONFIRMED.value,
                ReservationStatus.ALTERATION_REQUESTED.value,
                ReservationStatus.PENDING.value,
            ]),
            ReservationInfo.checkin_date < end,
            ReservationInfo.checkout_date > start,
        )
    ).scalars().all()
    
    reserved_days = 0
    reserved_date_set = set()
    for res in reservations:
        if res.checkin_date and res.checkout_date:
            current = max(res.checkin_date, start)
            res_end = min(res.checkout_date, end)
            while current < res_end:
                reserved_date_set.add(current)
                current += timedelta(days=1)
    reserved_days = len(reserved_date_set)
    
    # 차단된 날짜 수 (예약과 중복 제외)
    blocked_dates = db.execute(
        select(IcalBlockedDate.blocked_date).where(
            IcalBlockedDate.property_code == property_code,
            IcalBlockedDate.blocked_date >= start,
            IcalBlockedDate.blocked_date < end,
        )
    ).scalars().all()
    
    blocked_days = len([d for d in blocked_dates if d not in reserved_date_set])
    
    # 점유율
    occupied_days = reserved_days + blocked_days
    available_days = total_days - occupied_days
    occupancy_rate = (occupied_days / total_days * 100) if total_days > 0 else 0
    
    return OccupancyDTO(
        property_code=property_code,
        property_name=profile.name,
        period_start=start,
        period_end=end,
        occupancy_rate=round(occupancy_rate, 1),
        reserved_days=reserved_days,
        blocked_days=blocked_days,
        available_days=available_days,
        total_days=total_days,
    )


@router.post("/{property_code}/sync")
async def sync_ical(
    property_code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    iCal 수동 동기화 (백그라운드)
    
    즉시 응답 반환 후 백그라운드에서 동기화 실행.
    동기화 완료 후 달력 새로고침하면 반영됨.
    """
    # property 존재 확인
    profile = db.execute(
        select(PropertyProfile).where(
            PropertyProfile.property_code == property_code,
        )
    ).scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Property not found")
    
    if not profile.ical_url:
        raise HTTPException(status_code=400, detail="iCal URL not configured")
    
    # 백그라운드 태스크 등록
    background_tasks.add_task(_sync_ical_background, property_code)
    
    return {
        "message": "동기화 시작됨",
        "property_code": property_code,
    }


def _sync_ical_background(property_code: str):
    """
    iCal 동기화 백그라운드 태스크
    """
    import asyncio
    from app.db.session import SessionLocal
    
    # 별도 event loop 생성
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_sync_ical_async(property_code))
    finally:
        loop.close()


async def _sync_ical_async(property_code: str):
    """iCal 동기화 실제 로직"""
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        service = IcalService(db)
        synced_count = await service.sync_property(property_code)
        db.commit()
        logger.info(f"CALENDAR_API: Background sync completed: {property_code}, {synced_count} dates")
    except Exception as e:
        db.rollback()
        logger.error(f"CALENDAR_API: Background sync failed: {property_code}, error: {e}")
    finally:
        db.close()


@router.put("/{property_code}/ical-url")
def update_ical_url(
    property_code: str,
    request: IcalUrlUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    iCal URL 설정/업데이트
    """
    profile = db.execute(
        select(PropertyProfile).where(
            PropertyProfile.property_code == property_code,
        )
    ).scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_code}")
    
    profile.ical_url = request.ical_url
    profile.ical_last_synced_at = None  # 다시 동기화 필요
    
    db.commit()
    
    return {"message": "iCal URL updated", "property_code": property_code}


@router.post("/check-availability", response_model=AvailabilityCheckResponse)
def check_availability(
    request: AvailabilityCheckRequest,
    db: Session = Depends(get_db),
) -> AvailabilityCheckResponse:
    """
    예약 가능 여부 체크
    
    checkin_date ~ checkout_date 사이에 예약 또는 차단이 있는지 확인
    """
    property_code = request.property_code
    checkin = request.checkin_date
    checkout = request.checkout_date
    
    if checkout <= checkin:
        raise HTTPException(status_code=400, detail="checkout must be after checkin")
    
    conflicts: list[ConflictDTO] = []
    
    # 1. 예약 충돌 체크
    reservations = db.execute(
        select(ReservationInfo).where(
            ReservationInfo.property_code == property_code,
            ReservationInfo.status.in_([
                ReservationStatus.CONFIRMED.value,
                ReservationStatus.ALTERATION_REQUESTED.value,
                ReservationStatus.PENDING.value,
            ]),
            ReservationInfo.checkin_date < checkout,
            ReservationInfo.checkout_date > checkin,
        )
    ).scalars().all()
    
    for res in reservations:
        if res.checkin_date and res.checkout_date:
            # 충돌 날짜 계산
            conflict_start = max(res.checkin_date, checkin)
            conflict_end = min(res.checkout_date, checkout)
            current = conflict_start
            while current < conflict_end:
                conflicts.append(ConflictDTO(
                    date=current,
                    type="reservation",
                    guest_name=res.guest_name,
                ))
                current += timedelta(days=1)
    
    # 2. 차단 충돌 체크
    blocked_dates = db.execute(
        select(IcalBlockedDate).where(
            IcalBlockedDate.property_code == property_code,
            IcalBlockedDate.blocked_date >= checkin,
            IcalBlockedDate.blocked_date < checkout,
        )
    ).scalars().all()
    
    # 이미 예약 충돌로 추가된 날짜 제외
    conflict_dates = {c.date for c in conflicts}
    for bd in blocked_dates:
        if bd.blocked_date not in conflict_dates:
            conflicts.append(ConflictDTO(
                date=bd.blocked_date,
                type="blocked",
                summary=bd.summary,
            ))
    
    # 정렬
    conflicts.sort(key=lambda x: x.date)
    
    # 메시지 생성
    if not conflicts:
        message = f"{checkin} ~ {checkout} 예약 가능합니다."
        available = True
    else:
        # 충돌 요약
        reservation_conflicts = [c for c in conflicts if c.type == "reservation"]
        blocked_conflicts = [c for c in conflicts if c.type == "blocked"]
        
        parts = []
        if reservation_conflicts:
            guest_names = list(set(c.guest_name for c in reservation_conflicts if c.guest_name))
            if guest_names:
                parts.append(f"{', '.join(guest_names)}님 예약과 충돌")
            else:
                parts.append(f"기존 예약 {len(reservation_conflicts)}일 충돌")
        
        if blocked_conflicts:
            parts.append(f"차단 {len(blocked_conflicts)}일")
        
        message = f"예약 불가: {', '.join(parts)}"
        available = False
    
    return AvailabilityCheckResponse(
        available=available,
        conflicts=conflicts,
        message=message,
    )


@router.get("/properties/list")
def list_properties_with_calendar(
    db: Session = Depends(get_db),
):
    """
    달력이 있는 숙소 목록 (iCal URL 설정 여부 포함)
    """
    profiles = db.execute(
        select(PropertyProfile).where(
            PropertyProfile.is_active == True,
        ).order_by(PropertyProfile.property_code)
    ).scalars().all()
    
    return [
        {
            "property_code": p.property_code,
            "name": p.name,
            "has_ical": bool(p.ical_url),
            "last_synced_at": p.ical_last_synced_at,
        }
        for p in profiles
    ]
