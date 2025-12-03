from enum import Enum, auto
from typing import List, Optional

from pydantic import BaseModel


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
    """게스트 메시지에 대한 Intent 분류 결과."""

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