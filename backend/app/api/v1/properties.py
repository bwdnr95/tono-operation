# backend/app/api/v1/properties.py
"""
Property Profile, Property Groups & OTA Listing Mapping 관리 API

숙소 정보 등록/수정/조회 및 OTA 리스팅 연결
"""

from typing import Optional, List, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.domain.models.property_profile import PropertyProfile
from app.domain.models.property_group import PropertyGroup
from app.domain.models.ota_listing_mapping import OtaListingMapping
from app.repositories.property_group_repository import PropertyGroupRepository

router = APIRouter(prefix="/properties", tags=["properties"])


# ============================================================
# Property Group Schemas
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
    property_count: Optional[int] = None  # 소속 property 수
    
    class Config:
        from_attributes = True


class PropertyGroupListItem(BaseModel):
    """그룹 목록 조회용 간략 응답"""
    id: int
    group_code: str
    name: str
    is_active: bool
    property_count: int
    
    class Config:
        from_attributes = True


# ============================================================
# Schemas
# ============================================================

class PropertyProfileBase(BaseModel):
    property_code: str
    group_code: Optional[str] = None  # 🆕 소속 그룹 코드
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
    
    # iCal 연동
    ical_url: Optional[str] = None
    ical_last_synced_at: Optional[datetime] = None


class PropertyProfileCreate(PropertyProfileBase):
    pass


class PropertyProfileUpdate(BaseModel):
    name: Optional[str] = None
    locale: Optional[str] = None
    is_active: Optional[bool] = None
    
    checkin_from: Optional[str] = None
    checkout_until: Optional[str] = None
    checkin_method: Optional[str] = None
    
    address_full: Optional[str] = None
    address_summary: Optional[str] = None
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
    
    # iCal 연동
    ical_url: Optional[str] = None


class PropertyProfileResponse(PropertyProfileBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class OtaMappingBase(BaseModel):
    ota: str = "airbnb"
    listing_id: str
    listing_name: Optional[str] = None
    property_code: Optional[str] = None  # 그룹 매핑 시 NULL 가능
    group_code: Optional[str] = None  # 그룹 매핑용
    is_active: bool = True


class OtaMappingCreate(BaseModel):
    ota: str = "airbnb"
    listing_id: str
    listing_name: Optional[str] = None
    property_code: Optional[str] = None
    group_code: Optional[str] = None
    is_active: bool = True


class OtaMappingResponse(BaseModel):
    id: int
    ota: str
    listing_id: str
    listing_name: Optional[str] = None
    property_code: Optional[str] = None
    group_code: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================
# Property Profile Endpoints
# ============================================================

@router.get("", response_model=List[PropertyProfileResponse])
def list_properties(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """숙소 목록 조회"""
    query = db.query(PropertyProfile)
    
    if is_active is not None:
        query = query.filter(PropertyProfile.is_active == is_active)
    
    query = query.order_by(PropertyProfile.property_code)
    return query.all()


# ============================================================
# 고정 경로 (동적 경로 /{property_code} 보다 먼저 정의해야 함)
# ============================================================

@router.get("/all-ota-mappings", response_model=List[OtaMappingResponse])
def list_all_ota_mappings(
    ota: Optional[str] = None,
    group_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """전체 OTA 매핑 목록"""
    query = db.query(OtaListingMapping).filter(
        OtaListingMapping.is_active == True
    )
    
    if ota:
        query = query.filter(OtaListingMapping.ota == ota)
    
    if group_code:
        query = query.filter(OtaListingMapping.group_code == group_code)
    
    return query.order_by(OtaListingMapping.property_code).all()


class MappingTargetItem(BaseModel):
    """OTA 매핑 대상 (그룹 또는 숙소)"""
    type: str  # "group" | "property"
    code: str  # group_code 또는 property_code
    name: str
    group_code: Optional[str] = None  # property인 경우 소속 그룹


@router.get("/mapping-targets", response_model=List[MappingTargetItem])
def list_mapping_targets(
    db: Session = Depends(get_db),
):
    """
    OTA 매핑 선택용 - 그룹 + 독립 숙소 통합 목록
    """
    result = []
    
    # 1. 그룹 목록
    groups = db.query(PropertyGroup).filter(
        PropertyGroup.is_active == True
    ).order_by(PropertyGroup.group_code).all()
    
    for group in groups:
        result.append(MappingTargetItem(
            type="group",
            code=group.group_code,
            name=f"📁 {group.name}",
            group_code=None,
        ))
    
    # 2. 숙소 목록 (그룹 소속 포함)
    properties = db.query(PropertyProfile).filter(
        PropertyProfile.is_active == True
    ).order_by(PropertyProfile.property_code).all()
    
    for prop in properties:
        result.append(MappingTargetItem(
            type="property",
            code=prop.property_code,
            name=f"🏠 {prop.name}",
            group_code=prop.group_code,
        ))
    
    return result


@router.post("/ota-mappings", response_model=OtaMappingResponse, status_code=201)
def create_ota_mapping(
    data: OtaMappingCreate,
    db: Session = Depends(get_db),
):
    """OTA 매핑 생성"""
    # 유효성 검사: property_code와 group_code 중 최소 하나는 필요
    if not data.property_code and not data.group_code:
        raise HTTPException(
            status_code=400,
            detail="property_code와 group_code 중 최소 하나는 필요합니다"
        )
    
    # 중복 체크
    existing = db.query(OtaListingMapping).filter(
        OtaListingMapping.ota == data.ota,
        OtaListingMapping.listing_id == data.listing_id,
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Mapping for {data.ota}:{data.listing_id} already exists"
        )
    
    # property_code가 있으면 해당 property의 group_code 자동 설정
    if data.property_code:
        prop = db.query(PropertyProfile).filter(
            PropertyProfile.property_code == data.property_code
        ).first()
        if prop and prop.group_code and not data.group_code:
            data_dict = data.model_dump()
            data_dict["group_code"] = prop.group_code
            mapping = OtaListingMapping(**data_dict)
        else:
            mapping = OtaListingMapping(**data.model_dump())
    else:
        mapping = OtaListingMapping(**data.model_dump())
    
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    
    return mapping


@router.delete("/ota-mappings/{mapping_id}", status_code=204)
def delete_ota_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
):
    """OTA 매핑 삭제"""
    mapping = db.query(OtaListingMapping).filter(
        OtaListingMapping.id == mapping_id
    ).first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    mapping.is_active = False
    mapping.updated_at = datetime.utcnow()
    db.commit()
    
    return None


# ============================================================
# 동적 경로 /{property_code}
# ============================================================

@router.get("/{property_code}", response_model=PropertyProfileResponse)
def get_property(
    property_code: str,
    db: Session = Depends(get_db),
):
    """숙소 상세 조회"""
    prop = db.query(PropertyProfile).filter(
        PropertyProfile.property_code == property_code
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return prop


@router.post("", response_model=PropertyProfileResponse, status_code=201)
def create_property(
    data: PropertyProfileCreate,
    db: Session = Depends(get_db),
):
    """숙소 생성"""
    # 중복 체크
    existing = db.query(PropertyProfile).filter(
        PropertyProfile.property_code == data.property_code
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Property code '{data.property_code}' already exists"
        )
    
    prop = PropertyProfile(**data.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    
    return prop


@router.put("/{property_code}", response_model=PropertyProfileResponse)
def update_property(
    property_code: str,
    data: PropertyProfileUpdate,
    db: Session = Depends(get_db),
):
    """숙소 수정"""
    prop = db.query(PropertyProfile).filter(
        PropertyProfile.property_code == property_code
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # None이 아닌 필드만 업데이트
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prop, field, value)
    
    prop.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prop)
    
    return prop


@router.delete("/{property_code}", status_code=204)
def delete_property(
    property_code: str,
    db: Session = Depends(get_db),
):
    """숙소 삭제 (soft delete - is_active=False)"""
    prop = db.query(PropertyProfile).filter(
        PropertyProfile.property_code == property_code
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    prop.is_active = False
    prop.updated_at = datetime.utcnow()
    db.commit()
    
    return None


# ============================================================
# OTA Listing Mapping Endpoints
# ============================================================

@router.get("/{property_code}/ota-mappings", response_model=List[OtaMappingResponse])
def list_ota_mappings(
    property_code: str,
    db: Session = Depends(get_db),
):
    """특정 숙소의 OTA 매핑 목록"""
    mappings = db.query(OtaListingMapping).filter(
        OtaListingMapping.property_code == property_code,
        OtaListingMapping.is_active == True,
    ).all()
    
    return mappings
