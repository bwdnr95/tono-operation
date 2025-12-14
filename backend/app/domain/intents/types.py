# backend/app/domain/intents/types.py
from enum import Enum, auto
from typing import List, Optional

from pydantic import BaseModel


# ------------------------------------------------------------
# 1. 기존 1차 Intent (DB, 서비스 전체에서 이미 사용 중)
#    → 절대 이름/개수/의미 안 건드림
# ------------------------------------------------------------

class MessageIntent(Enum):
    CHECKIN_QUESTION = auto()        # 체크인 시간/방법 문의
    CHECKOUT_QUESTION = auto()       # 체크아웃 관련 문의
    RESERVATION_CHANGE = auto()      # 날짜/인원 변경 요청
    CANCELLATION = auto()            # 취소 관련
    COMPLAINT = auto()               # 클레임/불만
    LOCATION_QUESTION = auto()       # 위치/길찾기 문의
    AMENITY_QUESTION = auto()        # 수건/비품/시설 관련 문의
    PET_POLICY_QUESTION = auto()     # 반려동물 동반/정책 문의
    GENERAL_QUESTION = auto()        # 일반 문의 (기타 질문)
    THANKS_OR_GOOD_REVIEW = auto()   # 감사 인사 / 긍정 피드백
    OTHER = auto()                   # 기타 (분류 불가)
    HOUSE_RULE_QUESTION = auto()     # 하우스 룰 관련 문의


class MessageIntentResult(BaseModel):
    """게스트 메시지에 대한 1차 Intent 분류 결과 (기존 TONO 포맷)."""

    intent: MessageIntent
    confidence: float  # 0.0 ~ 1.0
    reasons: List[str]

    is_ambiguous: bool = False

    secondary_intent: Optional[MessageIntent] = None
    secondary_confidence: Optional[float] = None


class IntentLabelSource(Enum):
    """해당 Intent 라벨이 어디서 왔는지 구분하기 위한 소스 구분자."""
    SYSTEM = "system"      # TONO 엔진이 자동 분류한 값
    HUMAN = "human"        # 예약실/운영자가 직접 지정
    ML = "ml"              # ML 모델이 제안한 값
    CORRECTED = "corrected"  # 시스템 값에서 사람이 수정한 최종값


# ------------------------------------------------------------
# 2. V3+: 세분화 Fine-Grained Intent (LLM 내부 용도 + 고급 분석용)
#    - DB Enum과는 분리된, TONO 내부 어휘층
# ------------------------------------------------------------

class FineGrainedIntent(str, Enum):
    # --- 체크인 / 체크아웃 / 체류 관련 ---
    CHECKIN_TIME_QUESTION = "CHECKIN_TIME_QUESTION"          # 체크인 시간 문의
    CHECKIN_METHOD_QUESTION = "CHECKIN_METHOD_QUESTION"      # 입실 방법(비밀번호, 키수령) 문의
    EARLY_CHECKIN_REQUEST = "EARLY_CHECKIN_REQUEST"          # 얼리 체크인 요청
    LATE_CHECKIN_REQUEST = "LATE_CHECKIN_REQUEST"            # 아주 늦은 시간 체크인 문의

    CHECKOUT_TIME_QUESTION = "CHECKOUT_TIME_QUESTION"        # 체크아웃 시간 문의
    LATE_CHECKOUT_REQUEST = "LATE_CHECKOUT_REQUEST"          # 레이트 체크아웃 요청
    BAGGAGE_STORAGE_REQUEST = "BAGGAGE_STORAGE_REQUEST"      # 짐 보관 문의

    # --- 예약 변경/취소 ---
    DATE_CHANGE_REQUEST = "DATE_CHANGE_REQUEST"              # 날짜 변경 요청
    GUEST_COUNT_CHANGE_REQUEST = "GUEST_COUNT_CHANGE_REQUEST"  # 인원 변경 요청
    EXTEND_STAY_REQUEST = "EXTEND_STAY_REQUEST"              # 연장 숙박 요청
    SHORTEN_STAY_REQUEST = "SHORTEN_STAY_REQUEST"            # 일정 단축

    CANCELLATION_REQUEST = "CANCELLATION_REQUEST"            # 예약 취소 요청
    CANCELLATION_POLICY_QUESTION = "CANCELLATION_POLICY_QUESTION"  # 취소/환불 규정 문의

    # --- 클레임 / 문제 제기 ---
    CLEANLINESS_COMPLAINT = "CLEANLINESS_COMPLAINT"          # 청소/위생 문제
    NOISE_COMPLAINT = "NOISE_COMPLAINT"                      # 소음 민원
    FACILITY_BROKEN_COMPLAINT = "FACILITY_BROKEN_COMPLAINT"  # 고장/작동 안 됨
    OVERCHARGE_COMPLAINT = "OVERCHARGE_COMPLAINT"            # 요금/결제 관련 클레임
    HOST_ATTITUDE_COMPLAINT = "HOST_ATTITUDE_COMPLAINT"      # 응대 태도 불만
    SAFETY_SECURITY_COMPLAINT = "SAFETY_SECURITY_COMPLAINT"  # 안전/보안 문제

    # --- 위치 / 이동 / 주차 ---
    LOCATION_DIRECTION_QUESTION = "LOCATION_DIRECTION_QUESTION"  # 위치/찾아오는 길
    PARKING_QUESTION = "PARKING_QUESTION"                        # 주차 가능 여부 / 수
    NEARBY_SPOTS_QUESTION = "NEARBY_SPOTS_QUESTION"              # 주변 관광/편의시설 문의

    # --- 편의시설 / 장비 ---
    WIFI_QUESTION = "WIFI_QUESTION"                          # 와이파이, 비밀번호
    BEDDING_TOWEL_QUESTION = "BEDDING_TOWEL_QUESTION"        # 침구/수건 추가 여부
    HEATING_COOLING_QUESTION = "HEATING_COOLING_QUESTION"    # 난방/에어컨
    KITCHEN_EQUIPMENT_QUESTION = "KITCHEN_EQUIPMENT_QUESTION"  # 취사도구/조리 가능
    LAUNDRY_QUESTION = "LAUNDRY_QUESTION"                    # 세탁기/건조기 사용
    AMENITY_OTHER_QUESTION = "AMENITY_OTHER_QUESTION"        # 기타 편의시설 문의

    # --- 반려동물 ---
    PET_ALLOWED_QUESTION = "PET_ALLOWED_QUESTION"            # 반려동물 동반 가능 여부
    PET_EXTRA_FEE_QUESTION = "PET_EXTRA_FEE_QUESTION"        # 반려동물 추가요금
    PET_SIZE_RESTRICTION_QUESTION = "PET_SIZE_RESTRICTION_QUESTION"  # 크기/마릿수 제한

    # --- 하우스 룰 ---
    HOUSE_RULE_SMOKING_QUESTION = "HOUSE_RULE_SMOKING_QUESTION"     # 흡연 가능/구역 문의
    HOUSE_RULE_PARTY_QUESTION = "HOUSE_RULE_PARTY_QUESTION"         # 파티/행사 가능 여부
    HOUSE_RULE_VISITOR_QUESTION = "HOUSE_RULE_VISITOR_QUESTION"     # 외부인 방문 가능 여부
    HOUSE_RULE_NOISE_QUESTION = "HOUSE_RULE_NOISE_QUESTION"         # 소음/조용시간 관련 룰

    # --- 일반 문의 / 인사 / 리뷰 ---
    GENERAL_GREETING = "GENERAL_GREETING"                    # 단순 인사, 체크인 전 안부 등
    GENERAL_THANKS = "GENERAL_THANKS"                        # 감사 인사
    GENERAL_POSITIVE_FEEDBACK = "GENERAL_POSITIVE_FEEDBACK"  # 긍정 리뷰/칭찬
    GENERAL_OTHER_QUESTION = "GENERAL_OTHER_QUESTION"        # 위에 안 잡히는 일반 문의

    OTHER = "OTHER"                                          # 분류 불가/애매


class FineGrainedIntentResult(BaseModel):
    """
    LLM이 세분화 Intent 까지 분류했을 때 사용하는 고급 결과 포맷.

    - fine_intent: 세분화 Intent (FineGrainedIntent)
    - primary_intent: 기존 TONO MessageIntent (DB/서비스 호환용)
    """

    fine_intent: FineGrainedIntent
    primary_intent: MessageIntent

    confidence: float
    reasons: List[str]

    is_ambiguous: bool = False


# ------------------------------------------------------------
# 3. FineGrainedIntent → 기존 MessageIntent 매핑
#    (LLM / 분석에서 공통으로 사용)
# ------------------------------------------------------------

_FINE_TO_PRIMARY_MAP: dict[FineGrainedIntent, MessageIntent] = {
    # 체크인/체크아웃 계열 → CHECKIN / CHECKOUT
    FineGrainedIntent.CHECKIN_TIME_QUESTION: MessageIntent.CHECKIN_QUESTION,
    FineGrainedIntent.CHECKIN_METHOD_QUESTION: MessageIntent.CHECKIN_QUESTION,
    FineGrainedIntent.EARLY_CHECKIN_REQUEST: MessageIntent.CHECKIN_QUESTION,
    FineGrainedIntent.LATE_CHECKIN_REQUEST: MessageIntent.CHECKIN_QUESTION,

    FineGrainedIntent.CHECKOUT_TIME_QUESTION: MessageIntent.CHECKOUT_QUESTION,
    FineGrainedIntent.LATE_CHECKOUT_REQUEST: MessageIntent.CHECKOUT_QUESTION,
    FineGrainedIntent.BAGGAGE_STORAGE_REQUEST: MessageIntent.CHECKOUT_QUESTION,

    # 예약 변경/취소 계열
    FineGrainedIntent.DATE_CHANGE_REQUEST: MessageIntent.RESERVATION_CHANGE,
    FineGrainedIntent.GUEST_COUNT_CHANGE_REQUEST: MessageIntent.RESERVATION_CHANGE,
    FineGrainedIntent.EXTEND_STAY_REQUEST: MessageIntent.RESERVATION_CHANGE,
    FineGrainedIntent.SHORTEN_STAY_REQUEST: MessageIntent.RESERVATION_CHANGE,

    FineGrainedIntent.CANCELLATION_REQUEST: MessageIntent.CANCELLATION,
    FineGrainedIntent.CANCELLATION_POLICY_QUESTION: MessageIntent.CANCELLATION,

    # 클레임 계열
    FineGrainedIntent.CLEANLINESS_COMPLAINT: MessageIntent.COMPLAINT,
    FineGrainedIntent.NOISE_COMPLAINT: MessageIntent.COMPLAINT,
    FineGrainedIntent.FACILITY_BROKEN_COMPLAINT: MessageIntent.COMPLAINT,
    FineGrainedIntent.OVERCHARGE_COMPLAINT: MessageIntent.COMPLAINT,
    FineGrainedIntent.HOST_ATTITUDE_COMPLAINT: MessageIntent.COMPLAINT,
    FineGrainedIntent.SAFETY_SECURITY_COMPLAINT: MessageIntent.COMPLAINT,

    # 위치/주차
    FineGrainedIntent.LOCATION_DIRECTION_QUESTION: MessageIntent.LOCATION_QUESTION,
    FineGrainedIntent.PARKING_QUESTION: MessageIntent.LOCATION_QUESTION,
    FineGrainedIntent.NEARBY_SPOTS_QUESTION: MessageIntent.LOCATION_QUESTION,

    # 편의시설
    FineGrainedIntent.WIFI_QUESTION: MessageIntent.AMENITY_QUESTION,
    FineGrainedIntent.BEDDING_TOWEL_QUESTION: MessageIntent.AMENITY_QUESTION,
    FineGrainedIntent.HEATING_COOLING_QUESTION: MessageIntent.AMENITY_QUESTION,
    FineGrainedIntent.KITCHEN_EQUIPMENT_QUESTION: MessageIntent.AMENITY_QUESTION,
    FineGrainedIntent.LAUNDRY_QUESTION: MessageIntent.AMENITY_QUESTION,
    FineGrainedIntent.AMENITY_OTHER_QUESTION: MessageIntent.AMENITY_QUESTION,

    # 반려동물
    FineGrainedIntent.PET_ALLOWED_QUESTION: MessageIntent.PET_POLICY_QUESTION,
    FineGrainedIntent.PET_EXTRA_FEE_QUESTION: MessageIntent.PET_POLICY_QUESTION,
    FineGrainedIntent.PET_SIZE_RESTRICTION_QUESTION: MessageIntent.PET_POLICY_QUESTION,

    # 하우스 룰 → HOUSE_RULE_QUESTION 기본, 일부는 COMPLAINT와도 연결 가능하지만 우선 룰 질문으로 매핑
    FineGrainedIntent.HOUSE_RULE_SMOKING_QUESTION: MessageIntent.HOUSE_RULE_QUESTION,
    FineGrainedIntent.HOUSE_RULE_PARTY_QUESTION: MessageIntent.HOUSE_RULE_QUESTION,
    FineGrainedIntent.HOUSE_RULE_VISITOR_QUESTION: MessageIntent.HOUSE_RULE_QUESTION,
    FineGrainedIntent.HOUSE_RULE_NOISE_QUESTION: MessageIntent.HOUSE_RULE_QUESTION,

    # 일반/인사/리뷰
    FineGrainedIntent.GENERAL_GREETING: MessageIntent.GENERAL_QUESTION,
    FineGrainedIntent.GENERAL_THANKS: MessageIntent.THANKS_OR_GOOD_REVIEW,
    FineGrainedIntent.GENERAL_POSITIVE_FEEDBACK: MessageIntent.THANKS_OR_GOOD_REVIEW,
    FineGrainedIntent.GENERAL_OTHER_QUESTION: MessageIntent.GENERAL_QUESTION,

    # 기타
    FineGrainedIntent.OTHER: MessageIntent.OTHER,
}


def map_fine_to_primary_intent(fine: FineGrainedIntent) -> MessageIntent:
    """
    세분화 Intent → 기존 1차 Intent 로 매핑.

    - 매핑 테이블에 없더라도 기본값 OTHER 로 fallback
    - 모든 LLM/분석 코드에서 공통으로 이 함수를 사용하도록 강제
    """
    return _FINE_TO_PRIMARY_MAP.get(fine, MessageIntent.OTHER)
