# backend/app/domain/enums/answer_pack_keys.py
"""
Answer Pack Key Definitions

LLM이 선택할 수 있는 정보 유형 Key 정의.
- DB 컬럼명이 아닌 업무 단위 key 사용
- LLM은 이 목록에서만 선택 가능 (임의 생성 불가)
"""
from enum import Enum


class AnswerPackKey(str, Enum):
    """
    Answer Pack Key (19개)
    
    LLM 1차 호출에서 게스트 메시지 분석 후 선택.
    선택된 key에 해당하는 정보만 2차 호출에 주입.
    """
    
    # ===== 체크인/체크아웃 (5개) =====
    CHECKIN_INFO = "checkin_info"      # checkin_from, checkin_method, access_guide
    CHECKOUT_INFO = "checkout_info"    # checkout_until
    EARLY_CHECKIN = "early_checkin"    # FAQ에서 조회
    LATE_CHECKOUT = "late_checkout"    # FAQ에서 조회
    LUGGAGE_STORAGE = "luggage_storage"  # FAQ에서 조회
    
    # ===== 위치 (2개) =====
    LOCATION_INFO = "location_info"    # address_summary, location_guide
    ADDRESS_DETAIL = "address_detail"  # address_full (⚠️ 노출 조건 제한)
    
    # ===== 시설 (4개) =====
    WIFI_INFO = "wifi_info"            # wifi_ssid, wifi_password
    PARKING_INFO = "parking_info"      # parking_info
    ROOM_INFO = "room_info"            # bedroom_count, bed_count, bed_types, bathroom_count, capacity_base, capacity_max, floor_plan
    AMENITIES_INFO = "amenities_info"  # towel_count_provided, has_tv, has_projector, has_turntable, has_wine_opener, has_terrace, has_elevator
    
    # ===== 가전/사용법 (3개) =====
    APPLIANCE_GUIDE = "appliance_guide"  # aircon_count, aircon_usage_guide, heating_usage_guide
    KITCHEN_INFO = "kitchen_info"        # cooking_allowed, has_seasonings, has_tableware, has_rice_cooker
    LAUNDRY_INFO = "laundry_info"        # has_washer, has_dryer, laundry_guide
    
    # ===== 특수 시설 (2개) =====
    POOL_INFO = "pool_info"            # has_pool, hot_pool_fee_info
    BBQ_INFO = "bbq_info"              # bbq_available, bbq_guide
    
    # ===== 정책 (3개) =====
    PET_POLICY = "pet_policy"          # pet_allowed, pet_policy
    HOUSE_RULES = "house_rules"        # smoking_policy, noise_policy, house_rules
    EXTRA_BEDDING = "extra_bedding"    # extra_bedding_available, extra_bedding_price_info
    
    # ❌ PAYMENT_REFUND는 제외 → Safety/Orchestrator에서 처리


# Fallback Sets (전체 주입 금지)
DEFAULT_FALLBACK_KEYS = [
    AnswerPackKey.CHECKIN_INFO,
    AnswerPackKey.WIFI_INFO,
    AnswerPackKey.PARKING_INFO,
    AnswerPackKey.HOUSE_RULES,
]

COMPLEX_FALLBACK_KEYS = [
    AnswerPackKey.CHECKIN_INFO,
    AnswerPackKey.CHECKOUT_INFO,
    AnswerPackKey.LOCATION_INFO,
    AnswerPackKey.HOUSE_RULES,
]


# Key 설명 (LLM 프롬프트용)
ANSWER_PACK_KEY_DESCRIPTIONS = {
    AnswerPackKey.CHECKIN_INFO: "체크인 시간, 방법, 출입 가이드",
    AnswerPackKey.CHECKOUT_INFO: "체크아웃 시간",
    AnswerPackKey.EARLY_CHECKIN: "얼리체크인 가능 여부, 비용",
    AnswerPackKey.LATE_CHECKOUT: "레이트체크아웃 가능 여부, 비용",
    AnswerPackKey.LUGGAGE_STORAGE: "짐 보관 가능 여부",
    AnswerPackKey.LOCATION_INFO: "위치, 주변 정보",
    AnswerPackKey.ADDRESS_DETAIL: "상세 주소",
    AnswerPackKey.WIFI_INFO: "와이파이 SSID, 비밀번호",
    AnswerPackKey.PARKING_INFO: "주차 정보",
    AnswerPackKey.ROOM_INFO: "객실 구성, 수용 인원",
    AnswerPackKey.AMENITIES_INFO: "편의시설 (TV, 빔프로젝터, 수건 등)",
    AnswerPackKey.APPLIANCE_GUIDE: "에어컨, 난방 사용법",
    AnswerPackKey.KITCHEN_INFO: "조리 가능 여부, 주방용품",
    AnswerPackKey.LAUNDRY_INFO: "세탁기, 건조기 정보",
    AnswerPackKey.POOL_INFO: "수영장/온수풀 정보",
    AnswerPackKey.BBQ_INFO: "바베큐 정보",
    AnswerPackKey.PET_POLICY: "반려동물 정책",
    AnswerPackKey.HOUSE_RULES: "흡연, 소음, 숙소 규칙",
    AnswerPackKey.EXTRA_BEDDING: "추가 침구 정보",
}
