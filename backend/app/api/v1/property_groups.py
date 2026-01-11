# backend/app/api/v1/property_groups.py
"""
Property Groups 관리 API

숙소 그룹 CRUD 및 그룹-숙소 연결
별도 라우터로 분리하여 라우트 충돌 방지
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.models.property_profile import PropertyProfile
from app.domain.models.property_group import PropertyGroup

router = APIRouter(prefix="/property-groups", tags=["property-groups"])


# ============================================================
# Schemas
# ============================================================

class PropertyGroupBase(BaseModel):
    group_code: str
    name: str
    locale: str = "ko-KR"
    is_active: bool = True
    
    # 체크인/체크아웃
    checkin_from: Optional[str] = None
    checkout_until: Optional[str] = None
    checkin_method: Optional[str] = None
    
    # 위치/주소
    address_full: Optional[str] = None
    address_summary: Optional[str] = None
    address_disclosure_policy: Optional[str] = "checkin_day"
    location_guide: Optional[str] = None
    access_guide: Optional[str] = None
    
    # 공간/구조
    floor_plan: Optional[str] = None
    bedroom_count: Optional[int] = None
    bed_count: Optional[int] = None
    bed_types: Optional[str] = None
    bathroom_count: Optional[int] = None
    has_elevator: Optional[bool] = None
    capacity_base: Optional[int] = None
    capacity_max: Optional[int] = None
    has_terrace: Optional[bool] = None
    
    # 네트워크/편의
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None
    towel_count_provided: Optional[int] = None
    aircon_count: Optional[int] = None
    aircon_usage_guide: Optional[str] = None
    heating_usage_guide: Optional[str] = None
    
    # 추가 침구
    extra_bedding_available: Optional[bool] = None
    extra_bedding_price_info: Optional[str] = None
    
    # 세탁/조리
    laundry_guide: Optional[str] = None
    has_washer: Optional[bool] = None
    has_dryer: Optional[bool] = None
    cooking_allowed: Optional[bool] = None
    has_seasonings: Optional[bool] = None
    has_tableware: Optional[bool] = None
    has_rice_cooker: Optional[bool] = None
    
    # 엔터테인먼트
    has_tv: Optional[bool] = None
    has_projector: Optional[bool] = None
    has_turntable: Optional[bool] = None
    has_wine_opener: Optional[bool] = None
    
    # 수영장/바베큐
    has_pool: Optional[bool] = None
    hot_pool_fee_info: Optional[str] = None  # Deprecated: 하위 호환용
    pool_fee: Optional[str] = None
    pool_reservation_notice: Optional[str] = None
    pool_payment_account: Optional[str] = None
    bbq_available: Optional[bool] = None
    bbq_guide: Optional[str] = None  # Deprecated: 하위 호환용
    bbq_fee: Optional[str] = None
    bbq_reservation_notice: Optional[str] = None
    bbq_payment_account: Optional[str] = None
    
    # 정책
    parking_info: Optional[str] = None
    pet_allowed: Optional[bool] = None
    pet_policy: Optional[str] = None
    smoking_policy: Optional[str] = None
    noise_policy: Optional[str] = None
    house_rules: Optional[str] = None
    space_overview: Optional[str] = None
    
    # JSON
    amenities: Optional[dict] = None
    extra_metadata: Optional[dict] = None
    faq_entries: Optional[list] = None


class PropertyGroupCreate(PropertyGroupBase):
    pass


class PropertyGroupUpdate(BaseModel):
    name: Optional[str] = None
    locale: Optional[str] = None
    is_active: Optional[bool] = None
    
    checkin_from: Optional[str] = None
    checkout_until: Optional[str] = None
    checkin_method: Optional[str] = None
    
    address_full: Optional[str] = None
    address_summary: Optional[str] = None
    address_disclosure_policy: Optional[str] = None
    location_guide: Optional[str] = None
    access_guide: Optional[str] = None
    
    floor_plan: Optional[str] = None
    bedroom_count: Optional[int] = None
    bed_count: Optional[int] = None
    bed_types: Optional[str] = None
    bathroom_count: Optional[int] = None
    has_elevator: Optional[bool] = None
    capacity_base: Optional[int] = None
    capacity_max: Optional[int] = None
    has_terrace: Optional[bool] = None
    
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None
    towel_count_provided: Optional[int] = None
    aircon_count: Optional[int] = None
    aircon_usage_guide: Optional[str] = None
    heating_usage_guide: Optional[str] = None
    
    extra_bedding_available: Optional[bool] = None
    extra_bedding_price_info: Optional[str] = None
    
    laundry_guide: Optional[str] = None
    has_washer: Optional[bool] = None
    has_dryer: Optional[bool] = None
    cooking_allowed: Optional[bool] = None
    has_seasonings: Optional[bool] = None
    has_tableware: Optional[bool] = None
    has_rice_cooker: Optional[bool] = None
    
    has_tv: Optional[bool] = None
    has_projector: Optional[bool] = None
    has_turntable: Optional[bool] = None
    has_wine_opener: Optional[bool] = None
    
    has_pool: Optional[bool] = None
    hot_pool_fee_info: Optional[str] = None
    pool_fee: Optional[str] = None
    pool_reservation_notice: Optional[str] = None
    pool_payment_account: Optional[str] = None
    bbq_available: Optional[bool] = None
    bbq_guide: Optional[str] = None
    bbq_fee: Optional[str] = None
    bbq_reservation_notice: Optional[str] = None
    bbq_payment_account: Optional[str] = None
    
    parking_info: Optional[str] = None
    pet_allowed: Optional[bool] = None
    pet_policy: Optional[str] = None
    smoking_policy: Optional[str] = None
    noise_policy: Optional[str] = None
    house_rules: Optional[str] = None
    space_overview: Optional[str] = None
    
    amenities: Optional[dict] = None
    extra_metadata: Optional[dict] = None
    faq_entries: Optional[list] = None


class PropertyGroupResponse(PropertyGroupBase):
    id: int
    created_at: datetime
    updated_at: datetime
    property_count: Optional[int] = None
    
    class Config:
        from_attributes = True


class PropertyGroupListItem(BaseModel):
    id: int
    group_code: str
    name: str
    is_active: bool
    property_count: int
    
    class Config:
        from_attributes = True


class PropertyInGroupResponse(BaseModel):
    id: int
    property_code: str
    name: str
    bed_types: Optional[str] = None
    capacity_max: Optional[int] = None
    is_active: bool
    
    class Config:
        from_attributes = True


# ============================================================
# Endpoints
# ============================================================

@router.get("", response_model=List[PropertyGroupListItem])
def list_property_groups(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """숙소 그룹 목록 조회"""
    query = db.query(PropertyGroup)
    
    if is_active is not None:
        query = query.filter(PropertyGroup.is_active == is_active)
    
    groups = query.order_by(PropertyGroup.group_code).all()
    
    result = []
    for group in groups:
        property_count = db.query(PropertyProfile).filter(
            PropertyProfile.group_code == group.group_code,
            PropertyProfile.is_active == True,
        ).count()
        
        result.append(PropertyGroupListItem(
            id=group.id,
            group_code=group.group_code,
            name=group.name,
            is_active=group.is_active,
            property_count=property_count,
        ))
    
    return result


@router.get("/{group_code}", response_model=PropertyGroupResponse)
def get_property_group(
    group_code: str,
    db: Session = Depends(get_db),
):
    """숙소 그룹 상세 조회"""
    group = db.query(PropertyGroup).filter(
        PropertyGroup.group_code == group_code
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Property group not found")
    
    property_count = db.query(PropertyProfile).filter(
        PropertyProfile.group_code == group_code,
        PropertyProfile.is_active == True,
    ).count()
    
    response = PropertyGroupResponse.model_validate(group)
    response.property_count = property_count
    
    return response


@router.post("", response_model=PropertyGroupResponse, status_code=201)
def create_property_group(
    data: PropertyGroupCreate,
    db: Session = Depends(get_db),
):
    """숙소 그룹 생성"""
    existing = db.query(PropertyGroup).filter(
        PropertyGroup.group_code == data.group_code
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Group code '{data.group_code}' already exists"
        )
    
    group = PropertyGroup(**data.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    
    response = PropertyGroupResponse.model_validate(group)
    response.property_count = 0
    
    return response


@router.put("/{group_code}", response_model=PropertyGroupResponse)
def update_property_group(
    group_code: str,
    data: PropertyGroupUpdate,
    db: Session = Depends(get_db),
):
    """숙소 그룹 수정"""
    group = db.query(PropertyGroup).filter(
        PropertyGroup.group_code == group_code
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Property group not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)
    
    group.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(group)
    
    property_count = db.query(PropertyProfile).filter(
        PropertyProfile.group_code == group_code,
        PropertyProfile.is_active == True,
    ).count()
    
    response = PropertyGroupResponse.model_validate(group)
    response.property_count = property_count
    
    return response


@router.delete("/{group_code}", status_code=204)
def delete_property_group(
    group_code: str,
    db: Session = Depends(get_db),
):
    """숙소 그룹 삭제 (soft delete)"""
    group = db.query(PropertyGroup).filter(
        PropertyGroup.group_code == group_code
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Property group not found")
    
    group.is_active = False
    group.updated_at = datetime.utcnow()
    db.commit()
    
    return None


@router.get("/{group_code}/properties", response_model=List[PropertyInGroupResponse])
def list_properties_in_group(
    group_code: str,
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
):
    """특정 그룹에 속한 숙소 목록"""
    group = db.query(PropertyGroup).filter(
        PropertyGroup.group_code == group_code
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Property group not found")
    
    query = db.query(PropertyProfile).filter(
        PropertyProfile.group_code == group_code
    )
    
    if is_active is not None:
        query = query.filter(PropertyProfile.is_active == is_active)
    
    return query.order_by(PropertyProfile.property_code).all()


@router.post("/{group_code}/properties/{property_code}", status_code=200)
def add_property_to_group(
    group_code: str,
    property_code: str,
    db: Session = Depends(get_db),
):
    """숙소를 그룹에 추가"""
    group = db.query(PropertyGroup).filter(
        PropertyGroup.group_code == group_code
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Property group not found")
    
    prop = db.query(PropertyProfile).filter(
        PropertyProfile.property_code == property_code
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    prop.group_code = group_code
    prop.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Property '{property_code}' added to group '{group_code}'"}


@router.delete("/{group_code}/properties/{property_code}", status_code=200)
def remove_property_from_group(
    group_code: str,
    property_code: str,
    db: Session = Depends(get_db),
):
    """숙소를 그룹에서 제거"""
    prop = db.query(PropertyProfile).filter(
        PropertyProfile.property_code == property_code,
        PropertyProfile.group_code == group_code,
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found in this group")
    
    prop.group_code = None
    prop.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Property '{property_code}' removed from group '{group_code}'"}
