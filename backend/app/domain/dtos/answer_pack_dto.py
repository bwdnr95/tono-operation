# backend/app/domain/dtos/answer_pack_dto.py
"""
Answer Pack DTOs

LLM에 주입되는 정보의 Pydantic 스키마.
- Dict[str, Any] 사용 금지
- 명확한 타입으로 프롬프트 형태 안정화
"""
from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 개별 Pack DTOs
# ═══════════════════════════════════════════════════════════════

class CheckinInfoPack(BaseModel):
    """체크인 정보 Pack"""
    checkin_from: Optional[str] = Field(None, description="체크인 시작 시간 (예: 15:00)")
    checkin_method: Optional[str] = Field(None, description="체크인 방식 (예: DOORLOCK_SELF_CHECKIN)")
    access_guide: Optional[str] = Field(None, description="출입 가이드")


class CheckoutInfoPack(BaseModel):
    """체크아웃 정보 Pack"""
    checkout_until: Optional[str] = Field(None, description="체크아웃 마감 시간 (예: 11:00)")


class WifiInfoPack(BaseModel):
    """와이파이 정보 Pack"""
    ssid: Optional[str] = Field(None, description="와이파이 네트워크 이름")
    password: Optional[str] = Field(None, description="와이파이 비밀번호")


class ParkingInfoPack(BaseModel):
    """주차 정보 Pack"""
    info: Optional[str] = Field(None, description="주차 관련 안내")


class RoomInfoPack(BaseModel):
    """객실 구성 정보 Pack"""
    bedroom_count: Optional[int] = Field(None, description="침실 개수")
    bed_count: Optional[int] = Field(None, description="침대 개수")
    bed_types: Optional[str] = Field(None, description="침대 타입 설명")
    bathroom_count: Optional[int] = Field(None, description="화장실 개수")
    capacity_base: Optional[int] = Field(None, description="기준 인원")
    capacity_max: Optional[int] = Field(None, description="최대 인원")
    floor_plan: Optional[str] = Field(None, description="집 구조 설명")


class AmenitiesInfoPack(BaseModel):
    """편의시설 정보 Pack"""
    towel_count: Optional[int] = Field(None, description="수건 개수")
    has_tv: bool = Field(False, description="TV 보유 여부")
    has_projector: bool = Field(False, description="빔프로젝터 보유 여부")
    has_turntable: bool = Field(False, description="턴테이블 보유 여부")
    has_wine_opener: bool = Field(False, description="와인오프너 보유 여부")
    has_terrace: bool = Field(False, description="테라스 보유 여부")
    has_elevator: bool = Field(False, description="엘리베이터 유무")


class ApplianceGuidePack(BaseModel):
    """가전제품 사용 안내 Pack"""
    aircon_count: Optional[int] = Field(None, description="에어컨 개수")
    aircon_usage_guide: Optional[str] = Field(None, description="에어컨 사용 안내")
    heating_usage_guide: Optional[str] = Field(None, description="난방 사용 안내")


class KitchenInfoPack(BaseModel):
    """주방 정보 Pack"""
    cooking_allowed: bool = Field(False, description="조리 가능 여부")
    has_seasonings: bool = Field(False, description="조미료 구비 여부")
    has_tableware: bool = Field(False, description="식기류 구비 여부")
    has_rice_cooker: bool = Field(False, description="밥솥 구비 여부")


class LaundryInfoPack(BaseModel):
    """세탁 정보 Pack"""
    has_washer: bool = Field(False, description="세탁기 보유 여부")
    has_dryer: bool = Field(False, description="건조기 보유 여부")
    laundry_guide: Optional[str] = Field(None, description="세탁 관련 안내")


class PoolInfoPack(BaseModel):
    """
    수영장/온수풀 정보 Pack (구조화)
    
    DB 컬럼에서 직접 읽어옴:
    - has_pool
    - pool_fee
    - pool_reservation_notice
    - pool_payment_account
    """
    has_pool: bool = Field(False, description="수영장 보유 여부")
    fee: Optional[str] = Field(None, description="이용료 (예: 100,000원)")
    reservation_notice: Optional[str] = Field(None, description="예약 조건 (예: 최소 2일 전 예약 필요)")
    payment_account: Optional[str] = Field(None, description="⭐ 입금 계좌 (예: 카카오뱅크 79420372489 송대섭)")


class BbqInfoPack(BaseModel):
    """
    바베큐 정보 Pack (구조화)
    
    DB 컬럼에서 직접 읽어옴:
    - bbq_available
    - bbq_fee
    - bbq_reservation_notice
    - bbq_payment_account
    """
    bbq_available: bool = Field(False, description="바베큐 이용 가능 여부")
    fee: Optional[str] = Field(None, description="이용료 (예: 30,000원)")
    reservation_notice: Optional[str] = Field(None, description="예약 조건 (예: 최소 1일 전 예약 필요)")
    payment_account: Optional[str] = Field(None, description="⭐ 입금 계좌 (예: 카카오뱅크 79420372489 송대섭)")


class PetPolicyPack(BaseModel):
    """반려동물 정책 Pack"""
    pet_allowed: bool = Field(False, description="반려동물 동반 가능 여부")
    policy: Optional[str] = Field(None, description="반려동물 관련 정책")


class HouseRulesPack(BaseModel):
    """숙소 규칙 Pack"""
    smoking_policy: Optional[str] = Field(None, description="흡연 정책")
    noise_policy: Optional[str] = Field(None, description="소음 정책")
    rules: Optional[str] = Field(None, description="기타 숙소 규칙")


class LocationInfoPack(BaseModel):
    """위치 정보 Pack"""
    address_summary: Optional[str] = Field(None, description="간단 주소/위치 설명")
    location_guide: Optional[str] = Field(None, description="위치 안내")


class AddressDetailPack(BaseModel):
    """상세 주소 Pack (조건부 노출)"""
    address_full: Optional[str] = Field(None, description="상세 주소")


class ExtraBeddingPack(BaseModel):
    """추가 침구 정보 Pack"""
    available: bool = Field(False, description="추가 침구 이용 가능 여부")
    price_info: Optional[str] = Field(None, description="추가 침구 비용 안내")


# ═══════════════════════════════════════════════════════════════
# FAQ Item DTO
# ═══════════════════════════════════════════════════════════════

class FaqItem(BaseModel):
    """FAQ 항목"""
    key: str = Field(..., description="FAQ 키")
    answer: str = Field(..., description="FAQ 답변")
    category: Optional[str] = Field(None, description="카테고리")


# ═══════════════════════════════════════════════════════════════
# 통합 DTO - LLM 2차 호출에 주입되는 최종 형태
# ═══════════════════════════════════════════════════════════════

class AnswerPackResult(BaseModel):
    """
    Tool Layer 반환 타입 - LLM에 주입되는 최종 형태
    
    선택된 key에 해당하는 필드만 값이 채워지고,
    선택되지 않은 필드는 None으로 유지됨.
    """
    # 체크인/체크아웃
    checkin_info: Optional[CheckinInfoPack] = None
    checkout_info: Optional[CheckoutInfoPack] = None
    
    # 시설
    wifi_info: Optional[WifiInfoPack] = None
    parking_info: Optional[ParkingInfoPack] = None
    room_info: Optional[RoomInfoPack] = None
    amenities_info: Optional[AmenitiesInfoPack] = None
    
    # 가전/사용법
    appliance_guide: Optional[ApplianceGuidePack] = None
    kitchen_info: Optional[KitchenInfoPack] = None
    laundry_info: Optional[LaundryInfoPack] = None
    
    # 특수 시설
    pool_info: Optional[PoolInfoPack] = None
    bbq_info: Optional[BbqInfoPack] = None
    
    # 정책
    pet_policy: Optional[PetPolicyPack] = None
    house_rules: Optional[HouseRulesPack] = None
    extra_bedding: Optional[ExtraBeddingPack] = None
    
    # 위치
    location_info: Optional[LocationInfoPack] = None
    address_detail: Optional[AddressDetailPack] = None
    
    # FAQ 기반 특수 항목 (pack_key로 매칭)
    early_checkin: Optional[str] = Field(None, description="얼리체크인 FAQ 답변")
    late_checkout: Optional[str] = Field(None, description="레이트체크아웃 FAQ 답변")
    luggage_storage: Optional[str] = Field(None, description="짐보관 FAQ 답변")
    
    # FAQ 추가 항목 (매칭되는 항목들)
    faq_items: List[FaqItem] = Field(default_factory=list, description="관련 FAQ 항목들")
    
    def to_prompt_dict(self) -> dict:
        """
        LLM 프롬프트에 삽입할 때 사용하는 간소화된 dict.
        None 값인 필드는 제외.
        """
        result = {}
        
        for field_name, field_value in self:
            if field_value is None:
                continue
            if field_name == "faq_items" and not field_value:
                continue
            if isinstance(field_value, BaseModel):
                # Pydantic 모델은 dict로 변환하되 None 값 제외
                pack_dict = {k: v for k, v in field_value.model_dump().items() if v is not None}
                if pack_dict:  # 비어있지 않은 경우만 추가
                    result[field_name] = pack_dict
            elif isinstance(field_value, list):
                if field_value:  # 비어있지 않은 리스트만
                    result[field_name] = [
                        item.model_dump() if isinstance(item, BaseModel) else item
                        for item in field_value
                    ]
            else:
                result[field_name] = field_value
        
        return result


# ═══════════════════════════════════════════════════════════════
# Key Selection Response DTO (1차 호출 응답)
# ═══════════════════════════════════════════════════════════════

class KeySelectionResponse(BaseModel):
    """LLM 1차 호출(Key 선택) 응답"""
    keys: List[str] = Field(default_factory=list, description="선택된 pack key 리스트")
