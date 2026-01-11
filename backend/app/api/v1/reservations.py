# backend/app/api/v1/reservations.py
"""
Reservation 관리 API

예약 정보 조회 및 객실 배정/변경
"""

from typing import Optional, List
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.db.session import get_db
from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
from app.domain.models.property_profile import PropertyProfile
from app.domain.models.property_group import PropertyGroup
from app.domain.models.ical_blocked_date import IcalBlockedDate

router = APIRouter(prefix="/reservations", tags=["reservations"])


# ============================================================
# Schemas
# ============================================================

class ReservationResponse(BaseModel):
    """예약 정보 응답"""
    id: int
    airbnb_thread_id: str
    status: str
    
    guest_name: Optional[str] = None
    guest_count: Optional[int] = None
    child_count: Optional[int] = None
    infant_count: Optional[int] = None
    pet_count: Optional[int] = None
    
    reservation_code: Optional[str] = None
    checkin_date: Optional[date] = None
    checkout_date: Optional[date] = None
    
    property_code: Optional[str] = None
    group_code: Optional[str] = None
    listing_id: Optional[str] = None
    listing_name: Optional[str] = None
    
    # 추가 정보
    property_name: Optional[str] = None  # JOIN으로 가져옴
    group_name: Optional[str] = None  # JOIN으로 가져옴
    room_assigned: bool = False  # property_code가 있으면 True
    
    # 🆕 실제 적용되는 그룹 코드 (group_code가 없어도 property의 group_code 반영)
    effective_group_code: Optional[str] = None
    can_reassign: bool = False  # 객실 재배정 가능 여부
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class RoomAssignRequest(BaseModel):
    """객실 배정 요청"""
    property_code: str


class AvailableRoom(BaseModel):
    """배정 가능한 객실"""
    property_code: str
    name: str
    bed_types: Optional[str] = None
    capacity_max: Optional[int] = None
    is_available: bool = True
    conflict_info: Optional[str] = None  # 충돌 예약 정보


class RoomAssignmentInfo(BaseModel):
    """객실 배정 정보"""
    reservation: ReservationResponse
    group: Optional[dict] = None  # 그룹 정보
    available_rooms: List[AvailableRoom] = []


class ReservationListResponse(BaseModel):
    """예약 목록 응답 (페이지네이션)"""
    items: List[ReservationResponse]
    total: int
    limit: int
    offset: int


# ============================================================
# Endpoints
# ============================================================

def _build_reservation_query(
    db: Session,
    status: Optional[str] = None,
    group_code: Optional[str] = None,
    property_code: Optional[str] = None,
    unassigned_only: bool = False,
    checkin_from: Optional[date] = None,
    checkin_to: Optional[date] = None,
    checkout_from: Optional[date] = None,
    checkout_to: Optional[date] = None,
    search: Optional[str] = None,
):
    """공통 쿼리 빌더"""
    query = db.query(ReservationInfo)
    
    if status:
        query = query.filter(ReservationInfo.status == status)
    
    if group_code:
        query = query.filter(ReservationInfo.group_code == group_code)
    
    if property_code:
        query = query.filter(ReservationInfo.property_code == property_code)
    
    if unassigned_only:
        query = query.filter(
            ReservationInfo.group_code.isnot(None),
            ReservationInfo.property_code.is_(None),
        )
    
    if checkin_from:
        query = query.filter(ReservationInfo.checkin_date >= checkin_from)
    
    if checkin_to:
        query = query.filter(ReservationInfo.checkin_date <= checkin_to)
    
    if checkout_from:
        query = query.filter(ReservationInfo.checkout_date >= checkout_from)
    
    if checkout_to:
        query = query.filter(ReservationInfo.checkout_date <= checkout_to)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                ReservationInfo.guest_name.ilike(search_pattern),
                ReservationInfo.reservation_code.ilike(search_pattern),
            )
        )
    
    return query


def _enrich_reservation_response(r: ReservationInfo, db: Session) -> ReservationResponse:
    """예약 정보에 property_name, group_name, effective_group_code 추가"""
    response = ReservationResponse(
        id=r.id,
        airbnb_thread_id=r.airbnb_thread_id,
        status=r.status,
        guest_name=r.guest_name,
        guest_count=r.guest_count,
        child_count=r.child_count,
        infant_count=r.infant_count,
        pet_count=r.pet_count,
        reservation_code=r.reservation_code,
        checkin_date=r.checkin_date,
        checkout_date=r.checkout_date,
        property_code=r.property_code,
        group_code=r.group_code,
        listing_id=r.listing_id,
        listing_name=r.listing_name,
        created_at=r.created_at,
        updated_at=r.updated_at,
        room_assigned=r.property_code is not None,
    )
    
    # effective_group_code 계산: group_code가 있으면 사용, 없으면 property의 group_code
    effective_group_code = r.group_code
    
    if r.property_code:
        prop = db.query(PropertyProfile).filter(
            PropertyProfile.property_code == r.property_code
        ).first()
        if prop:
            response.property_name = prop.name
            # property의 group_code로 effective_group_code 설정
            if not effective_group_code and prop.group_code:
                effective_group_code = prop.group_code
    
    response.effective_group_code = effective_group_code
    
    # can_reassign: effective_group_code가 있으면 재배정 가능
    response.can_reassign = effective_group_code is not None
    
    if r.group_code:
        group = db.query(PropertyGroup).filter(
            PropertyGroup.group_code == r.group_code
        ).first()
        if group:
            response.group_name = group.name
    elif effective_group_code:
        # group_code는 없지만 property의 group_code가 있는 경우
        group = db.query(PropertyGroup).filter(
            PropertyGroup.group_code == effective_group_code
        ).first()
        if group:
            response.group_name = group.name
    
    return response


@router.get("", response_model=List[ReservationResponse])
def list_reservations(
    status: Optional[str] = None,
    group_code: Optional[str] = None,
    property_code: Optional[str] = None,
    unassigned_only: bool = False,
    checkin_from: Optional[date] = None,
    checkin_to: Optional[date] = None,
    checkout_from: Optional[date] = None,
    checkout_to: Optional[date] = None,
    search: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    예약 목록 조회
    
    Args:
        status: 예약 상태 필터 (confirmed, awaiting_approval 등)
        group_code: 그룹 코드 필터
        property_code: 숙소 코드 필터
        unassigned_only: 객실 미배정만 (group_code는 있지만 property_code가 없는 경우)
        checkin_from: 체크인 시작일
        checkin_to: 체크인 종료일
        checkout_from: 체크아웃 시작일
        checkout_to: 체크아웃 종료일
        search: 게스트명 또는 예약코드 검색
        limit: 최대 결과 수
    """
    query = _build_reservation_query(
        db, status, group_code, property_code, unassigned_only,
        checkin_from, checkin_to, checkout_from, checkout_to, search
    )
    
    reservations = query.order_by(
        ReservationInfo.checkin_date.asc()
    ).limit(limit).all()
    
    return [_enrich_reservation_response(r, db) for r in reservations]


@router.get("/paginated", response_model=ReservationListResponse)
def list_reservations_paginated(
    status: Optional[str] = None,
    group_code: Optional[str] = None,
    property_code: Optional[str] = None,
    unassigned_only: bool = False,
    checkin_from: Optional[date] = None,
    checkin_to: Optional[date] = None,
    checkout_from: Optional[date] = None,
    checkout_to: Optional[date] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    예약 목록 조회 (페이지네이션)
    
    Args:
        status: 예약 상태 필터 (confirmed, awaiting_approval 등)
        group_code: 그룹 코드 필터
        property_code: 숙소 코드 필터
        unassigned_only: 객실 미배정만
        checkin_from: 체크인 시작일
        checkin_to: 체크인 종료일
        checkout_from: 체크아웃 시작일
        checkout_to: 체크아웃 종료일
        search: 게스트명 또는 예약코드 검색
        limit: 페이지 크기 (기본 50)
        offset: 시작 위치
    """
    query = _build_reservation_query(
        db, status, group_code, property_code, unassigned_only,
        checkin_from, checkin_to, checkout_from, checkout_to, search
    )
    
    # 전체 개수
    total = query.count()
    
    # 페이지네이션 적용
    reservations = query.order_by(
        ReservationInfo.checkin_date.asc()
    ).offset(offset).limit(limit).all()
    
    return ReservationListResponse(
        items=[_enrich_reservation_response(r, db) for r in reservations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{thread_id}", response_model=ReservationResponse)
def get_reservation(
    thread_id: str,
    db: Session = Depends(get_db),
):
    """예약 상세 조회"""
    r = db.query(ReservationInfo).filter(
        ReservationInfo.airbnb_thread_id == thread_id
    ).first()
    
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    response = ReservationResponse(
        id=r.id,
        airbnb_thread_id=r.airbnb_thread_id,
        status=r.status,
        guest_name=r.guest_name,
        guest_count=r.guest_count,
        child_count=r.child_count,
        infant_count=r.infant_count,
        pet_count=r.pet_count,
        reservation_code=r.reservation_code,
        checkin_date=r.checkin_date,
        checkout_date=r.checkout_date,
        property_code=r.property_code,
        group_code=r.group_code,
        listing_id=r.listing_id,
        listing_name=r.listing_name,
        created_at=r.created_at,
        updated_at=r.updated_at,
        room_assigned=r.property_code is not None,
    )
    
    # property_name
    if r.property_code:
        prop = db.query(PropertyProfile).filter(
            PropertyProfile.property_code == r.property_code
        ).first()
        if prop:
            response.property_name = prop.name
    
    # group_name
    if r.group_code:
        group = db.query(PropertyGroup).filter(
            PropertyGroup.group_code == r.group_code
        ).first()
        if group:
            response.group_name = group.name
    
    return response


@router.get("/{thread_id}/room-assignment", response_model=RoomAssignmentInfo)
def get_room_assignment_info(
    thread_id: str,
    db: Session = Depends(get_db),
):
    """
    객실 배정 정보 조회 (배정 가능한 객실 목록 포함)
    
    Returns:
        - reservation: 예약 정보
        - group: 그룹 정보 (그룹 소속인 경우)
        - available_rooms: 배정 가능한 객실 목록 (충돌 정보 포함)
    """
    r = db.query(ReservationInfo).filter(
        ReservationInfo.airbnb_thread_id == thread_id
    ).first()
    
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    # group_code 결정: reservation에서 먼저, 없으면 property에서 가져옴
    effective_group_code = r.group_code
    if not effective_group_code and r.property_code:
        prop = db.query(PropertyProfile).filter(
            PropertyProfile.property_code == r.property_code
        ).first()
        if prop:
            effective_group_code = prop.group_code
    
    # 기본 예약 정보
    reservation_response = ReservationResponse(
        id=r.id,
        airbnb_thread_id=r.airbnb_thread_id,
        status=r.status,
        guest_name=r.guest_name,
        guest_count=r.guest_count,
        child_count=r.child_count,
        infant_count=r.infant_count,
        pet_count=r.pet_count,
        reservation_code=r.reservation_code,
        checkin_date=r.checkin_date,
        checkout_date=r.checkout_date,
        property_code=r.property_code,
        group_code=effective_group_code,  # 실제 사용할 group_code
        listing_id=r.listing_id,
        listing_name=r.listing_name,
        created_at=r.created_at,
        updated_at=r.updated_at,
        room_assigned=r.property_code is not None,
    )
    
    result = RoomAssignmentInfo(
        reservation=reservation_response,
        group=None,
        available_rooms=[],
    )
    
    # 그룹 정보
    if effective_group_code:
        group = db.query(PropertyGroup).filter(
            PropertyGroup.group_code == effective_group_code
        ).first()
        if group:
            result.group = {
                "group_code": group.group_code,
                "name": group.name,
            }
            reservation_response.group_name = group.name
    
    # property_name
    if r.property_code:
        prop = db.query(PropertyProfile).filter(
            PropertyProfile.property_code == r.property_code
        ).first()
        if prop:
            reservation_response.property_name = prop.name
    
    # 배정 가능한 객실 목록 (그룹이 있는 경우만)
    if effective_group_code:
        properties = db.query(PropertyProfile).filter(
            PropertyProfile.group_code == effective_group_code,
            PropertyProfile.is_active == True,
        ).order_by(PropertyProfile.property_code).all()
        
        for prop in properties:
            # 해당 날짜에 충돌하는 예약 확인
            conflict = None
            if r.checkin_date and r.checkout_date:
                # 1. reservation_info에서 충돌 체크
                conflict_reservation = db.query(ReservationInfo).filter(
                    ReservationInfo.property_code == prop.property_code,
                    ReservationInfo.airbnb_thread_id != thread_id,  # 자기 자신 제외
                    ReservationInfo.status.in_(["confirmed", "awaiting_approval"]),
                    # 날짜 겹침 조건
                    ReservationInfo.checkin_date < r.checkout_date,
                    ReservationInfo.checkout_date > r.checkin_date,
                ).first()
                
                if conflict_reservation:
                    conflict = f"{conflict_reservation.guest_name or '게스트'} ({conflict_reservation.checkin_date} ~ {conflict_reservation.checkout_date})"
                
                # 2. iCal 차단 날짜 체크
                # 
                # 배경: 에어비앤비 예약 → PMS iCal 동기화 → 해당 객실 차단
                # 문제: 같은 예약인데 iCal 차단으로 인해 배정 불가로 표시됨
                # 
                # 해결: iCal만 차단되어 있고, 해당 property에 "다른 예약"이 없으면
                #       → 이 예약의 iCal 동기화일 가능성 높음 → 배정 허용
                if not conflict:
                    ical_blocked = db.query(IcalBlockedDate).filter(
                        IcalBlockedDate.property_code == prop.property_code,
                        IcalBlockedDate.blocked_date >= r.checkin_date,
                        IcalBlockedDate.blocked_date < r.checkout_date,
                    ).first()
                    
                    if ical_blocked:
                        # iCal 차단이 있을 때, 해당 property에 다른 reservation_info가 있는지 확인
                        other_reservation = db.query(ReservationInfo).filter(
                            ReservationInfo.property_code == prop.property_code,
                            ReservationInfo.airbnb_thread_id != thread_id,
                            ReservationInfo.status.in_(["confirmed", "awaiting_approval"]),
                            ReservationInfo.checkin_date < r.checkout_date,
                            ReservationInfo.checkout_date > r.checkin_date,
                        ).first()
                        
                        if other_reservation:
                            # 다른 예약이 있으면 진짜 충돌 (iCal + 예약)
                            conflict = f"예약 있음 ({other_reservation.checkin_date} ~ {other_reservation.checkout_date})"
                        else:
                            # 다른 예약이 없고 iCal만 차단 → "이 예약"의 동기화일 가능성
                            # → conflict를 None으로 유지하여 배정 허용
                            # 단, UI에 힌트 표시용으로 conflict_info는 설정하되 is_available=True
                            pass  # conflict = None 유지 → is_available=True
            
            result.available_rooms.append(AvailableRoom(
                property_code=prop.property_code,
                name=prop.name,
                bed_types=prop.bed_types,
                capacity_max=prop.capacity_max,
                is_available=conflict is None,
                conflict_info=conflict,
            ))
    
    return result


@router.patch("/{thread_id}/assign-room", response_model=ReservationResponse)
def assign_room(
    thread_id: str,
    data: RoomAssignRequest,
    db: Session = Depends(get_db),
):
    """
    객실 배정/변경
    
    Args:
        thread_id: 예약의 airbnb_thread_id
        data.property_code: 배정할 객실 코드
    """
    # 예약 조회
    r = db.query(ReservationInfo).filter(
        ReservationInfo.airbnb_thread_id == thread_id
    ).first()
    
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    # 객실 존재 확인
    prop = db.query(PropertyProfile).filter(
        PropertyProfile.property_code == data.property_code,
        PropertyProfile.is_active == True,
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # 현재 effective group_code 결정
    effective_group_code = r.group_code
    if not effective_group_code and r.property_code:
        current_prop = db.query(PropertyProfile).filter(
            PropertyProfile.property_code == r.property_code
        ).first()
        if current_prop:
            effective_group_code = current_prop.group_code
    
    # 그룹 일치 확인 (현재 그룹과 새 객실의 그룹이 같아야 함)
    if effective_group_code and prop.group_code != effective_group_code:
        raise HTTPException(
            status_code=400,
            detail=f"Property '{data.property_code}' does not belong to group '{effective_group_code}'"
        )
    
    # 날짜 충돌 확인
    if r.checkin_date and r.checkout_date:
        # 1. reservation_info에서 충돌 체크
        conflict = db.query(ReservationInfo).filter(
            ReservationInfo.property_code == data.property_code,
            ReservationInfo.airbnb_thread_id != thread_id,
            ReservationInfo.status.in_(["confirmed", "awaiting_approval"]),
            ReservationInfo.checkin_date < r.checkout_date,
            ReservationInfo.checkout_date > r.checkin_date,
        ).first()
        
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Room conflict: {conflict.guest_name or 'Guest'} ({conflict.checkin_date} ~ {conflict.checkout_date})"
            )
        
        # 2. iCal 차단 날짜 체크
        # (iCal만 차단되어 있고 다른 reservation이 없으면 → 이 예약의 동기화이므로 배정 허용)
        ical_blocked = db.query(IcalBlockedDate).filter(
            IcalBlockedDate.property_code == data.property_code,
            IcalBlockedDate.blocked_date >= r.checkin_date,
            IcalBlockedDate.blocked_date < r.checkout_date,
        ).first()
        
        if ical_blocked:
            # 다른 예약이 있는지 확인
            other_reservation = db.query(ReservationInfo).filter(
                ReservationInfo.property_code == data.property_code,
                ReservationInfo.airbnb_thread_id != thread_id,
                ReservationInfo.status.in_(["confirmed", "awaiting_approval"]),
                ReservationInfo.checkin_date < r.checkout_date,
                ReservationInfo.checkout_date > r.checkin_date,
            ).first()
            
            if other_reservation:
                # 다른 예약이 있으면 진짜 충돌
                raise HTTPException(
                    status_code=409,
                    detail=f"Room conflict: {other_reservation.guest_name or 'Guest'} ({other_reservation.checkin_date} ~ {other_reservation.checkout_date})"
                )
            # 다른 예약이 없으면 iCal만 차단 → 이 예약의 동기화이므로 배정 허용 (에러 없음)
    
    # 배정
    old_property_code = r.property_code
    r.property_code = data.property_code
    
    # property의 group_code 동기화 (그룹 없던 예약에 그룹 소속 객실 배정 시)
    if prop.group_code and not r.group_code:
        r.group_code = prop.group_code
    
    r.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(r)
    
    # 로깅
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"Room assigned: thread_id={thread_id}, "
        f"property_code={old_property_code} -> {data.property_code}"
    )
    
    # 응답 구성
    response = ReservationResponse(
        id=r.id,
        airbnb_thread_id=r.airbnb_thread_id,
        status=r.status,
        guest_name=r.guest_name,
        guest_count=r.guest_count,
        child_count=r.child_count,
        infant_count=r.infant_count,
        pet_count=r.pet_count,
        reservation_code=r.reservation_code,
        checkin_date=r.checkin_date,
        checkout_date=r.checkout_date,
        property_code=r.property_code,
        group_code=r.group_code,
        listing_id=r.listing_id,
        listing_name=r.listing_name,
        property_name=prop.name,
        created_at=r.created_at,
        updated_at=r.updated_at,
        room_assigned=True,
    )
    
    if r.group_code:
        group = db.query(PropertyGroup).filter(
            PropertyGroup.group_code == r.group_code
        ).first()
        if group:
            response.group_name = group.name
    
    return response


@router.delete("/{thread_id}/assign-room", response_model=ReservationResponse)
def unassign_room(
    thread_id: str,
    db: Session = Depends(get_db),
):
    """
    객실 배정 해제
    
    그룹은 유지하고 property_code만 NULL로 변경
    """
    r = db.query(ReservationInfo).filter(
        ReservationInfo.airbnb_thread_id == thread_id
    ).first()
    
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    if not r.property_code:
        raise HTTPException(status_code=400, detail="No room assigned")
    
    # 그룹 매핑이 아닌 경우 (독채) 배정 해제 불가
    if not r.group_code:
        raise HTTPException(
            status_code=400,
            detail="Cannot unassign room for non-group reservation"
        )
    
    old_property_code = r.property_code
    r.property_code = None
    r.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(r)
    
    # 로깅
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"Room unassigned: thread_id={thread_id}, "
        f"property_code={old_property_code} -> None"
    )
    
    # 응답 구성
    response = ReservationResponse(
        id=r.id,
        airbnb_thread_id=r.airbnb_thread_id,
        status=r.status,
        guest_name=r.guest_name,
        guest_count=r.guest_count,
        child_count=r.child_count,
        infant_count=r.infant_count,
        pet_count=r.pet_count,
        reservation_code=r.reservation_code,
        checkin_date=r.checkin_date,
        checkout_date=r.checkout_date,
        property_code=r.property_code,
        group_code=r.group_code,
        listing_id=r.listing_id,
        listing_name=r.listing_name,
        created_at=r.created_at,
        updated_at=r.updated_at,
        room_assigned=False,
    )
    
    if r.group_code:
        group = db.query(PropertyGroup).filter(
            PropertyGroup.group_code == r.group_code
        ).first()
        if group:
            response.group_name = group.name
    
    return response
