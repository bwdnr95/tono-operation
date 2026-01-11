# backend/app/services/property_answer_pack_service.py
"""
Property Answer Pack Service (Tool Layer)

LLM이 선택한 Answer Pack Key에 해당하는 정보만 DB에서 조회하여 반환.
- DB 컬럼 + amenities JSON + faq_entries 통합
- 선택적 정보 주입으로 토큰 절감
- ADDRESS_DETAIL 노출 조건 강제
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.domain.enums.answer_pack_keys import (
    AnswerPackKey,
    DEFAULT_FALLBACK_KEYS,
    COMPLEX_FALLBACK_KEYS,
)
from app.domain.dtos.answer_pack_dto import (
    AnswerPackResult,
    CheckinInfoPack,
    CheckoutInfoPack,
    WifiInfoPack,
    ParkingInfoPack,
    RoomInfoPack,
    AmenitiesInfoPack,
    ApplianceGuidePack,
    KitchenInfoPack,
    LaundryInfoPack,
    PoolInfoPack,
    BbqInfoPack,
    PetPolicyPack,
    HouseRulesPack,
    LocationInfoPack,
    AddressDetailPack,
    ExtraBeddingPack,
    FaqItem,
)
from app.domain.models.property_profile import PropertyProfile
from app.domain.models.property_group import PropertyGroup
from app.repositories.property_profile_repository import PropertyProfileRepository
from app.repositories.property_group_repository import PropertyGroupRepository

logger = logging.getLogger(__name__)


class PropertyAnswerPackService:
    """
    Answer Pack 조회 서비스 (Tool Layer)
    
    설계 원칙:
    - LLM은 DB 스키마를 몰라야 함 → 업무 단위 key로만 소통
    - 정보 주입은 항상 선택적 → 필요한 것만 반환
    - Pydantic으로 스키마 고정 → 프롬프트 형태 안정화
    - 전체 주입 Fallback 금지 → 제한된 Fallback set만 사용
    """
    
    def __init__(self, db: Session):
        self._db = db
        self._property_repo = PropertyProfileRepository(db)
        self._group_repo = PropertyGroupRepository(db)
    
    def get_pack(
        self,
        property_code: Optional[str],
        keys: List[AnswerPackKey],
        reservation_status: str = "UNKNOWN",
        group_code: Optional[str] = None,
    ) -> AnswerPackResult:
        """
        선택된 key에 해당하는 정보만 반환 (그룹 상속 지원)
        
        Args:
            property_code: 숙소 코드 (NULL 가능 - 그룹만 있는 경우)
            keys: 선택된 AnswerPackKey 리스트
            reservation_status: 예약 상태 (ADDRESS_DETAIL 노출 조건용)
                - UPCOMING, CHECKIN_DAY, IN_HOUSE, CHECKOUT_DAY, CHECKED_OUT
            group_code: 그룹 코드 (property_code가 없을 때 사용)
                
        Returns:
            AnswerPackResult: 선택된 key에 해당하는 정보만 채워진 DTO
            
        상속 규칙:
            - property 값 우선
            - NULL이면 group에서 상속
        """
        profile: Optional[PropertyProfile] = None
        group: Optional[PropertyGroup] = None
        
        # 1. property 조회
        if property_code:
            profile = self._property_repo.get_by_property_code(property_code)
            if profile and profile.group_code:
                # property에 group_code가 있으면 그룹도 조회
                group = self._group_repo.get_by_group_code(profile.group_code)
        
        # 2. property가 없고 group_code가 있으면 그룹만 조회
        if not profile and group_code:
            group = self._group_repo.get_by_group_code(group_code)
        
        # 3. 둘 다 없으면 빈 결과 반환
        if not profile and not group:
            logger.warning(
                f"Neither PropertyProfile nor PropertyGroup found: "
                f"property_code={property_code}, group_code={group_code}"
            )
            return AnswerPackResult()
        
        result = AnswerPackResult()
        
        for key in keys:
            # ADDRESS_DETAIL 노출 조건 체크
            if key == AnswerPackKey.ADDRESS_DETAIL:
                policy = self._get_effective_value(
                    profile, group, 'address_disclosure_policy'
                ) or 'checkin_day'
                if not self._can_disclose_address(policy, reservation_status):
                    logger.info(
                        f"ADDRESS_DETAIL blocked: policy={policy}, status={reservation_status}"
                    )
                    continue
            
            # Pack 데이터 추출 (그룹 상속 적용)
            pack_data = self._extract_pack_with_inheritance(profile, group, key)
            if pack_data:
                setattr(result, key.value, pack_data)
        
        # FAQ에서 pack_key 매칭되는 항목 추가 (그룹 FAQ도 포함)
        result.faq_items = self._get_matched_faqs_with_inheritance(profile, group, keys)
        
        # early_checkin, late_checkout, luggage_storage는 FAQ에서 별도 추출
        self._extract_special_faqs_with_inheritance(profile, group, keys, result)
        
        logger.info(
            f"AnswerPack built: property={property_code}, group={group_code or (profile.group_code if profile else None)}, "
            f"keys={[k.value for k in keys]}, "
            f"faq_items={len(result.faq_items)}"
        )
        
        return result
    
    def get_fallback_keys(self, is_complex: bool = False) -> List[AnswerPackKey]:
        """
        Fallback key set 반환 (전체 주입 금지)
        
        Args:
            is_complex: 복합 질문 여부
            
        Returns:
            제한된 Fallback key 리스트
        """
        return COMPLEX_FALLBACK_KEYS if is_complex else DEFAULT_FALLBACK_KEYS
    
    # ═══════════════════════════════════════════════════════════════
    # Group Inheritance Helpers
    # ═══════════════════════════════════════════════════════════════
    
    def _get_effective_value(
        self,
        profile: Optional[PropertyProfile],
        group: Optional[PropertyGroup],
        field_name: str,
    ):
        """
        상속 규칙 적용: property 값 우선, NULL이면 group에서 상속
        
        Args:
            profile: PropertyProfile (nullable)
            group: PropertyGroup (nullable)
            field_name: 필드명
            
        Returns:
            유효한 값 (property 우선, 없으면 group)
        """
        # 1. property 값 확인
        if profile:
            value = getattr(profile, field_name, None)
            if value is not None:
                return value
        
        # 2. group에서 상속
        if group:
            return getattr(group, field_name, None)
        
        return None
    
    def _extract_pack_with_inheritance(
        self,
        profile: Optional[PropertyProfile],
        group: Optional[PropertyGroup],
        key: AnswerPackKey,
    ):
        """그룹 상속을 적용하여 Pack 데이터 추출"""
        extractors = {
            AnswerPackKey.CHECKIN_INFO: self._extract_checkin_info_inherited,
            AnswerPackKey.CHECKOUT_INFO: self._extract_checkout_info_inherited,
            AnswerPackKey.WIFI_INFO: self._extract_wifi_info_inherited,
            AnswerPackKey.PARKING_INFO: self._extract_parking_info_inherited,
            AnswerPackKey.ROOM_INFO: self._extract_room_info_inherited,
            AnswerPackKey.AMENITIES_INFO: self._extract_amenities_info_inherited,
            AnswerPackKey.APPLIANCE_GUIDE: self._extract_appliance_guide_inherited,
            AnswerPackKey.KITCHEN_INFO: self._extract_kitchen_info_inherited,
            AnswerPackKey.LAUNDRY_INFO: self._extract_laundry_info_inherited,
            AnswerPackKey.POOL_INFO: self._extract_pool_info_inherited,
            AnswerPackKey.BBQ_INFO: self._extract_bbq_info_inherited,
            AnswerPackKey.PET_POLICY: self._extract_pet_policy_inherited,
            AnswerPackKey.HOUSE_RULES: self._extract_house_rules_inherited,
            AnswerPackKey.LOCATION_INFO: self._extract_location_info_inherited,
            AnswerPackKey.ADDRESS_DETAIL: self._extract_address_detail_inherited,
            AnswerPackKey.EXTRA_BEDDING: self._extract_extra_bedding_inherited,
        }
        
        extractor = extractors.get(key)
        if extractor:
            return extractor(profile, group)
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # Pack Extraction with Inheritance
    # ═══════════════════════════════════════════════════════════════
    
    def _extract_checkin_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> CheckinInfoPack:
        return CheckinInfoPack(
            checkin_from=self._get_effective_value(profile, group, 'checkin_from'),
            checkin_method=self._get_effective_value(profile, group, 'checkin_method'),
            access_guide=self._get_effective_value(profile, group, 'access_guide'),
        )
    
    def _extract_checkout_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> CheckoutInfoPack:
        return CheckoutInfoPack(
            checkout_until=self._get_effective_value(profile, group, 'checkout_until'),
        )
    
    def _extract_wifi_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> WifiInfoPack:
        return WifiInfoPack(
            ssid=self._get_effective_value(profile, group, 'wifi_ssid'),
            password=self._get_effective_value(profile, group, 'wifi_password'),
        )
    
    def _extract_parking_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> ParkingInfoPack:
        return ParkingInfoPack(
            info=self._get_effective_value(profile, group, 'parking_info'),
        )
    
    def _extract_room_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> RoomInfoPack:
        return RoomInfoPack(
            bedroom_count=self._get_effective_value(profile, group, 'bedroom_count'),
            bed_count=self._get_effective_value(profile, group, 'bed_count'),
            bed_types=self._get_effective_value(profile, group, 'bed_types'),
            bathroom_count=self._get_effective_value(profile, group, 'bathroom_count'),
            capacity_base=self._get_effective_value(profile, group, 'capacity_base'),
            capacity_max=self._get_effective_value(profile, group, 'capacity_max'),
            floor_plan=self._get_effective_value(profile, group, 'floor_plan'),
        )
    
    def _extract_amenities_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> AmenitiesInfoPack:
        return AmenitiesInfoPack(
            towel_count=self._get_effective_value(profile, group, 'towel_count_provided'),
            has_tv=self._get_effective_value(profile, group, 'has_tv') or False,
            has_projector=self._get_effective_value(profile, group, 'has_projector') or False,
            has_turntable=self._get_effective_value(profile, group, 'has_turntable') or False,
            has_wine_opener=self._get_effective_value(profile, group, 'has_wine_opener') or False,
            has_terrace=self._get_effective_value(profile, group, 'has_terrace') or False,
            has_elevator=self._get_effective_value(profile, group, 'has_elevator') or False,
        )
    
    def _extract_appliance_guide_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> ApplianceGuidePack:
        return ApplianceGuidePack(
            aircon_count=self._get_effective_value(profile, group, 'aircon_count'),
            aircon_usage_guide=self._get_effective_value(profile, group, 'aircon_usage_guide'),
            heating_usage_guide=self._get_effective_value(profile, group, 'heating_usage_guide'),
        )
    
    def _extract_kitchen_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> KitchenInfoPack:
        return KitchenInfoPack(
            cooking_allowed=self._get_effective_value(profile, group, 'cooking_allowed') or False,
            has_seasonings=self._get_effective_value(profile, group, 'has_seasonings') or False,
            has_tableware=self._get_effective_value(profile, group, 'has_tableware') or False,
            has_rice_cooker=self._get_effective_value(profile, group, 'has_rice_cooker') or False,
        )
    
    def _extract_laundry_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> LaundryInfoPack:
        return LaundryInfoPack(
            has_washer=self._get_effective_value(profile, group, 'has_washer') or False,
            has_dryer=self._get_effective_value(profile, group, 'has_dryer') or False,
            laundry_guide=self._get_effective_value(profile, group, 'laundry_guide'),
        )
    
    def _extract_pool_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> PoolInfoPack:
        """
        수영장/온수풀 정보 추출 (새 컬럼에서 직접 읽기)
        
        DB 컬럼:
        - has_pool: bool
        - pool_fee: str (예: "100,000원")
        - pool_reservation_notice: str (예: "최소 2일 전 예약 필요")
        - pool_payment_account: str (예: "카카오뱅크 79420372489 송대섭")
        """
        return PoolInfoPack(
            has_pool=self._get_effective_value(profile, group, 'has_pool') or False,
            fee=self._get_effective_value(profile, group, 'pool_fee'),
            reservation_notice=self._get_effective_value(profile, group, 'pool_reservation_notice'),
            payment_account=self._get_effective_value(profile, group, 'pool_payment_account'),
        )
    
    def _extract_bbq_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> BbqInfoPack:
        """
        바베큐 정보 추출 (새 컬럼에서 직접 읽기)
        
        DB 컬럼:
        - bbq_available: bool
        - bbq_fee: str (예: "30,000원")
        - bbq_reservation_notice: str (예: "최소 1일 전 예약 필요")
        - bbq_payment_account: str (예: "카카오뱅크 79420372489 송대섭")
        """
        return BbqInfoPack(
            bbq_available=self._get_effective_value(profile, group, 'bbq_available') or False,
            fee=self._get_effective_value(profile, group, 'bbq_fee'),
            reservation_notice=self._get_effective_value(profile, group, 'bbq_reservation_notice'),
            payment_account=self._get_effective_value(profile, group, 'bbq_payment_account'),
        )
    
    def _extract_pet_policy_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> PetPolicyPack:
        return PetPolicyPack(
            pet_allowed=self._get_effective_value(profile, group, 'pet_allowed') or False,
            policy=self._get_effective_value(profile, group, 'pet_policy'),
        )
    
    def _extract_house_rules_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> HouseRulesPack:
        return HouseRulesPack(
            smoking_policy=self._get_effective_value(profile, group, 'smoking_policy'),
            noise_policy=self._get_effective_value(profile, group, 'noise_policy'),
            rules=self._get_effective_value(profile, group, 'house_rules'),
        )
    
    def _extract_location_info_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> LocationInfoPack:
        return LocationInfoPack(
            address_summary=self._get_effective_value(profile, group, 'address_summary'),
            location_guide=self._get_effective_value(profile, group, 'location_guide'),
        )
    
    def _extract_address_detail_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> AddressDetailPack:
        return AddressDetailPack(
            address_full=self._get_effective_value(profile, group, 'address_full'),
        )
    
    def _extract_extra_bedding_inherited(
        self, profile: Optional[PropertyProfile], group: Optional[PropertyGroup]
    ) -> ExtraBeddingPack:
        return ExtraBeddingPack(
            available=self._get_effective_value(profile, group, 'extra_bedding_available') or False,
            price_info=self._get_effective_value(profile, group, 'extra_bedding_price_info'),
        )
    
    # ═══════════════════════════════════════════════════════════════
    # FAQ Integration with Inheritance
    # ═══════════════════════════════════════════════════════════════
    
    def _get_matched_faqs_with_inheritance(
        self,
        profile: Optional[PropertyProfile],
        group: Optional[PropertyGroup],
        keys: List[AnswerPackKey],
    ) -> List[FaqItem]:
        """
        그룹 상속을 적용하여 FAQ 항목 반환
        - property FAQ 우선
        - 같은 key의 FAQ가 없으면 group FAQ에서 가져옴
        """
        key_values = [k.value for k in keys]
        special_keys = {"early_checkin", "late_checkout", "luggage_storage"}
        
        matched = []
        matched_keys = set()  # 이미 매칭된 key 추적
        
        # 1. property FAQ 우선
        if profile and profile.faq_entries:
            for faq in profile.faq_entries:
                pack_key = faq.get("pack_key")
                if not pack_key or pack_key in special_keys:
                    continue
                if pack_key in key_values:
                    matched.append(FaqItem(
                        key=faq.get("key", ""),
                        answer=faq.get("answer", ""),
                        category=faq.get("category"),
                    ))
                    matched_keys.add(pack_key)
        
        # 2. group FAQ에서 보충 (property에 없는 것만)
        if group and group.faq_entries:
            for faq in group.faq_entries:
                pack_key = faq.get("pack_key")
                if not pack_key or pack_key in special_keys:
                    continue
                if pack_key in key_values and pack_key not in matched_keys:
                    matched.append(FaqItem(
                        key=faq.get("key", ""),
                        answer=faq.get("answer", ""),
                        category=faq.get("category"),
                    ))
                    matched_keys.add(pack_key)
        
        return matched
    
    def _extract_special_faqs_with_inheritance(
        self,
        profile: Optional[PropertyProfile],
        group: Optional[PropertyGroup],
        keys: List[AnswerPackKey],
        result: AnswerPackResult,
    ) -> None:
        """
        그룹 상속을 적용하여 special FAQ 추출
        """
        special_mapping = {
            "early_checkin": (AnswerPackKey.EARLY_CHECKIN, "early_checkin"),
            "late_checkout": (AnswerPackKey.LATE_CHECKOUT, "late_checkout"),
            "luggage_storage": (AnswerPackKey.LUGGAGE_STORAGE, "luggage_storage"),
        }
        
        found_keys = set()
        
        # 1. property FAQ 우선
        if profile and profile.faq_entries:
            for faq in profile.faq_entries:
                pack_key = faq.get("pack_key")
                if pack_key in special_mapping:
                    key_enum, attr_name = special_mapping[pack_key]
                    if key_enum in keys:
                        setattr(result, attr_name, faq.get("answer", ""))
                        found_keys.add(pack_key)
        
        # 2. group FAQ에서 보충
        if group and group.faq_entries:
            for faq in group.faq_entries:
                pack_key = faq.get("pack_key")
                if pack_key in special_mapping and pack_key not in found_keys:
                    key_enum, attr_name = special_mapping[pack_key]
                    if key_enum in keys:
                        setattr(result, attr_name, faq.get("answer", ""))
    
    # ═══════════════════════════════════════════════════════════════
    # Address Disclosure Policy
    # ═══════════════════════════════════════════════════════════════
    
    def _can_disclose_address(self, policy: str, status: str) -> bool:
        """
        주소 노출 가능 여부 판단
        
        정책:
        - always: 예약 확정 시점부터 노출
        - checkin_day: 체크인 당일부터 노출 (기본값)
        
        Args:
            policy: 'always' | 'checkin_day'
            status: 예약 상태
            
        Returns:
            노출 가능 여부
        """
        if policy == "always":
            # 예약 확정된 모든 상태에서 노출
            return status in ["UPCOMING", "CHECKIN_DAY", "IN_HOUSE", "CHECKOUT_DAY"]
        
        # checkin_day (기본값): 체크인 당일부터만 노출
        return status in ["CHECKIN_DAY", "IN_HOUSE", "CHECKOUT_DAY"]
    
    # ═══════════════════════════════════════════════════════════════
    # Pack Extraction (Legacy - single profile, no inheritance)
    # ═══════════════════════════════════════════════════════════════
    
    def _extract_pack(self, profile: PropertyProfile, key: AnswerPackKey):
        """key에 해당하는 Pack 데이터 추출"""
        extractors = {
            AnswerPackKey.CHECKIN_INFO: self._extract_checkin_info,
            AnswerPackKey.CHECKOUT_INFO: self._extract_checkout_info,
            AnswerPackKey.WIFI_INFO: self._extract_wifi_info,
            AnswerPackKey.PARKING_INFO: self._extract_parking_info,
            AnswerPackKey.ROOM_INFO: self._extract_room_info,
            AnswerPackKey.AMENITIES_INFO: self._extract_amenities_info,
            AnswerPackKey.APPLIANCE_GUIDE: self._extract_appliance_guide,
            AnswerPackKey.KITCHEN_INFO: self._extract_kitchen_info,
            AnswerPackKey.LAUNDRY_INFO: self._extract_laundry_info,
            AnswerPackKey.POOL_INFO: self._extract_pool_info,
            AnswerPackKey.BBQ_INFO: self._extract_bbq_info,
            AnswerPackKey.PET_POLICY: self._extract_pet_policy,
            AnswerPackKey.HOUSE_RULES: self._extract_house_rules,
            AnswerPackKey.LOCATION_INFO: self._extract_location_info,
            AnswerPackKey.ADDRESS_DETAIL: self._extract_address_detail,
            AnswerPackKey.EXTRA_BEDDING: self._extract_extra_bedding,
            # early_checkin, late_checkout, luggage_storage는 FAQ에서 추출
        }
        
        extractor = extractors.get(key)
        if extractor:
            return extractor(profile)
        return None
    
    def _extract_checkin_info(self, profile: PropertyProfile) -> CheckinInfoPack:
        return CheckinInfoPack(
            checkin_from=profile.checkin_from,
            checkin_method=profile.checkin_method,
            access_guide=profile.access_guide,
        )
    
    def _extract_checkout_info(self, profile: PropertyProfile) -> CheckoutInfoPack:
        return CheckoutInfoPack(
            checkout_until=profile.checkout_until,
        )
    
    def _extract_wifi_info(self, profile: PropertyProfile) -> WifiInfoPack:
        return WifiInfoPack(
            ssid=profile.wifi_ssid,
            password=profile.wifi_password,
        )
    
    def _extract_parking_info(self, profile: PropertyProfile) -> ParkingInfoPack:
        return ParkingInfoPack(
            info=profile.parking_info,
        )
    
    def _extract_room_info(self, profile: PropertyProfile) -> RoomInfoPack:
        return RoomInfoPack(
            bedroom_count=profile.bedroom_count,
            bed_count=profile.bed_count,
            bed_types=profile.bed_types,
            bathroom_count=profile.bathroom_count,
            capacity_base=profile.capacity_base,
            capacity_max=profile.capacity_max,
            floor_plan=profile.floor_plan,
        )
    
    def _extract_amenities_info(self, profile: PropertyProfile) -> AmenitiesInfoPack:
        return AmenitiesInfoPack(
            towel_count=profile.towel_count_provided,
            has_tv=profile.has_tv or False,
            has_projector=profile.has_projector or False,
            has_turntable=profile.has_turntable or False,
            has_wine_opener=profile.has_wine_opener or False,
            has_terrace=profile.has_terrace or False,
            has_elevator=profile.has_elevator or False,
        )
    
    def _extract_appliance_guide(self, profile: PropertyProfile) -> ApplianceGuidePack:
        return ApplianceGuidePack(
            aircon_count=profile.aircon_count,
            aircon_usage_guide=profile.aircon_usage_guide,
            heating_usage_guide=profile.heating_usage_guide,
        )
    
    def _extract_kitchen_info(self, profile: PropertyProfile) -> KitchenInfoPack:
        return KitchenInfoPack(
            cooking_allowed=profile.cooking_allowed or False,
            has_seasonings=profile.has_seasonings or False,
            has_tableware=profile.has_tableware or False,
            has_rice_cooker=profile.has_rice_cooker or False,
        )
    
    def _extract_laundry_info(self, profile: PropertyProfile) -> LaundryInfoPack:
        return LaundryInfoPack(
            has_washer=profile.has_washer or False,
            has_dryer=profile.has_dryer or False,
            laundry_guide=profile.laundry_guide,
        )
    
    def _extract_pool_info(self, profile: PropertyProfile) -> PoolInfoPack:
        """수영장/온수풀 정보 추출 (새 컬럼에서 직접 읽기)"""
        return PoolInfoPack(
            has_pool=profile.has_pool or False,
            fee=profile.pool_fee,
            reservation_notice=profile.pool_reservation_notice,
            payment_account=profile.pool_payment_account,
        )
    
    def _extract_bbq_info(self, profile: PropertyProfile) -> BbqInfoPack:
        """바베큐 정보 추출 (새 컬럼에서 직접 읽기)"""
        return BbqInfoPack(
            bbq_available=profile.bbq_available or False,
            fee=profile.bbq_fee,
            reservation_notice=profile.bbq_reservation_notice,
            payment_account=profile.bbq_payment_account,
        )
    
    def _extract_pet_policy(self, profile: PropertyProfile) -> PetPolicyPack:
        return PetPolicyPack(
            pet_allowed=profile.pet_allowed or False,
            policy=profile.pet_policy,
        )
    
    def _extract_house_rules(self, profile: PropertyProfile) -> HouseRulesPack:
        return HouseRulesPack(
            smoking_policy=profile.smoking_policy,
            noise_policy=profile.noise_policy,
            rules=profile.house_rules,
        )
    
    def _extract_location_info(self, profile: PropertyProfile) -> LocationInfoPack:
        return LocationInfoPack(
            address_summary=profile.address_summary,
            location_guide=profile.location_guide,
        )
    
    def _extract_address_detail(self, profile: PropertyProfile) -> AddressDetailPack:
        return AddressDetailPack(
            address_full=profile.address_full,
        )
    
    def _extract_extra_bedding(self, profile: PropertyProfile) -> ExtraBeddingPack:
        return ExtraBeddingPack(
            available=profile.extra_bedding_available or False,
            price_info=profile.extra_bedding_price_info,
        )
    
    # ═══════════════════════════════════════════════════════════════
    # FAQ Integration (Legacy)
    # ═══════════════════════════════════════════════════════════════
    
    def _get_matched_faqs(
        self,
        profile: PropertyProfile,
        keys: List[AnswerPackKey],
    ) -> List[FaqItem]:
        """
        pack_key가 매칭되는 FAQ 항목 반환
        
        Args:
            profile: PropertyProfile
            keys: 선택된 AnswerPackKey 리스트
            
        Returns:
            매칭된 FaqItem 리스트
        """
        faq_entries = profile.faq_entries or []
        key_values = [k.value for k in keys]
        
        # 특수 FAQ key 제외 (별도 처리됨)
        special_keys = {"early_checkin", "late_checkout", "luggage_storage"}
        
        matched = []
        for faq in faq_entries:
            pack_key = faq.get("pack_key")
            
            # pack_key가 없거나 특수 key인 경우 스킵
            if not pack_key or pack_key in special_keys:
                continue
            
            # 선택된 key와 매칭되는 경우만 포함
            if pack_key in key_values:
                matched.append(FaqItem(
                    key=faq.get("key", ""),
                    answer=faq.get("answer", ""),
                    category=faq.get("category"),
                ))
        
        return matched
    
    def _extract_special_faqs(
        self,
        profile: PropertyProfile,
        keys: List[AnswerPackKey],
        result: AnswerPackResult,
    ) -> None:
        """
        early_checkin, late_checkout, luggage_storage FAQ 추출
        
        이 3개는 FAQ에서 직접 가져와 AnswerPackResult의 전용 필드에 저장
        """
        faq_entries = profile.faq_entries or []
        
        for faq in faq_entries:
            pack_key = faq.get("pack_key")
            answer = faq.get("answer", "")
            
            if pack_key == "early_checkin" and AnswerPackKey.EARLY_CHECKIN in keys:
                result.early_checkin = answer
            elif pack_key == "late_checkout" and AnswerPackKey.LATE_CHECKOUT in keys:
                result.late_checkout = answer
            elif pack_key == "luggage_storage" and AnswerPackKey.LUGGAGE_STORAGE in keys:
                result.luggage_storage = answer
