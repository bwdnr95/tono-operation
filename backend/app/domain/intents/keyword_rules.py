
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from app.domain.intents import MessageIntent


TextScope = Literal["pure", "full", "both"]


@dataclass
class KeywordRule:
    """
    Intent 하나에 대한 키워드 기반 룰.

    - keywords: 매칭 대상 키워드들
    - scope:
        "pure" → 순수 게스트 메시지에서만 검사
        "full" → 전체 텍스트(템플릿 포함)에서만 검사
        "both" → 둘 다 검사
    - base_score: 이 룰이 매칭되었을 때 부여할 기본 점수
    - requires: AND 조건으로 반드시 포함되어야 하는 키워드 리스트 (선택)
    - negatives: 포함되면 오히려 감점을 주거나 무시해야 할 키워드 리스트 (선택)
    """

    keywords: List[str]
    scope: TextScope = "pure"
    base_score: float = 0.8
    requires: List[str] = field(default_factory=list)
    negatives: List[str] = field(default_factory=list)


@dataclass
class IntentRuleConfig:
    """
    Intent 하나에 대한 전체 룰 구성.
    - keyword_rules: 여러 개의 KeywordRule 을 OR 조건으로 묶을 수 있음
    - max_score: 이 Intent 가 가질 수 있는 최대 점수 (디폴트 1.0)
    """

    intent: MessageIntent
    keyword_rules: List[KeywordRule]
    max_score: float = 1.0


def get_default_intent_rules() -> Dict[MessageIntent, IntentRuleConfig]:
    """
    Airbnb 게스트 메시지에 대한 기본 Intent 룰셋.

    나중에:
    - 이 함수 내용을 DB/JSON/YAML 기반으로 교체할 수 있음
    - OTA/언어/숙소별로 다른 룰셋을 로딩하는 것도 가능
    """

    rules: Dict[MessageIntent, IntentRuleConfig] = {}

    # PET_POLICY_QUESTION
    rules[MessageIntent.PET_POLICY_QUESTION] = IntentRuleConfig(
        intent=MessageIntent.PET_POLICY_QUESTION,
        max_score=1.0,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "반려동물",
                    "반려 동물",
                    "애견",
                    "애완견",
                    "강아지",
                    "개를 데리고",
                    "강아지를 데리고",
                    "동반 입실",
                    "동반입실",
                    "동반 가능",
                    "동반해도 될까요",
                    "펫",
                    "pet",
                    "dog",
                ],
                scope="pure",
                base_score=0.95,
            ),
            KeywordRule(
                keywords=[
                    "동물",
                    "고양이",
                    "냥이",
                    "댕댕이",
                    "동반",
                    "동반해서",
                    "같이 데리고",
                ],
                scope="pure",
                base_score=0.85,
                requires=["예약"],  # '예약'이라는 단어가 같이 있을 때만 유효
            ),
        ],
    )

    # CHECKIN_QUESTION
    rules[MessageIntent.CHECKIN_QUESTION] = IntentRuleConfig(
        intent=MessageIntent.CHECKIN_QUESTION,
        max_score=0.9,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "체크인",
                    "입실 가능",
                    "얼리 체크인",
                    "조기 체크인",
                    "몇 시에 들어가",
                    "몇시에 들어가",
                    "몇시 에 들어가",
                    "키를 받",
                    "도착 시간이",
                    "짐을 먼저",
                    "짐 맡겨",
                ],
                scope="pure",  # 순수 게스트 메시지에서만 체크
                base_score=0.9,
            ),
        ],
    )

    # CHECKOUT_QUESTION
    rules[MessageIntent.CHECKOUT_QUESTION] = IntentRuleConfig(
        intent=MessageIntent.CHECKOUT_QUESTION,
        max_score=0.9,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "체크아웃",
                    "퇴실",
                    "늦게 나가",
                    "레이트 체크아웃",
                    "연장해서 나가",
                    "몇 시에 나가",
                    "몇시에 나가",
                    "몇시 까지 나가",
                ],
                scope="pure",
                base_score=0.9,
            ),
        ],
    )

    # RESERVATION_CHANGE
    rules[MessageIntent.RESERVATION_CHANGE] = IntentRuleConfig(
        intent=MessageIntent.RESERVATION_CHANGE,
        max_score=0.9,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "날짜 변경",
                    "날짜를 변경",
                    "일정 변경",
                    "일정을 변경",
                    "인원 변경",
                    "인원을 변경",
                    "한 명 더",
                    "한명 더",
                    "명 더 추가",
                    "하루 더",
                    "연장 하고 싶",
                    "연장하고 싶",
                    "하루 줄이",
                    "밤 줄이",
                    "줄이고 싶",
                ],
                scope="both",
                base_score=0.9,
            ),
        ],
    )

    # CANCELLATION
    rules[MessageIntent.CANCELLATION] = IntentRuleConfig(
        intent=MessageIntent.CANCELLATION,
        max_score=0.95,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "예약 취소",
                    "취소 하고 싶",
                    "취소하고 싶",
                    "예약을 취소",
                    "환불",
                    "노쇼",
                    "못 갈 것",
                    "못갈 것",
                    "방문이 어렵",
                ],
                scope="both",
                base_score=0.95,
            ),
        ],
    )

    # COMPLAINT
    rules[MessageIntent.COMPLAINT] = IntentRuleConfig(
        intent=MessageIntent.COMPLAINT,
        max_score=0.95,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "불편",
                    "문제",
                    "고장",
                    "작동 하지 않",
                    "작동하지 않",
                    "안 나와요",
                    "안 나옵니다",
                    "안 됩니다",
                    "안됩니다",
                    "시끄럽",
                    "소음",
                    "더럽",
                    "청소가",
                    "냄새가",
                    "곰팡이",
                    "벌레",
                    "곤충",
                    "모기",
                    "침구가",
                    "이불이",
                    "난방이",
                ],
                scope="pure",
                base_score=0.95,
            ),
        ],
    )

    # LOCATION_QUESTION
    rules[MessageIntent.LOCATION_QUESTION] = IntentRuleConfig(
        intent=MessageIntent.LOCATION_QUESTION,
        max_score=0.9,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "위치가",
                    "어디인가요",
                    "어디 인가요",
                    "어디쯤",
                    "가는 길",
                    "길 안내",
                    "찾아가는",
                    "오시는 길",
                    "네비",
                    "내비",
                    "주차",
                    "주차장",
                    "주차는 가",
                    "주차 가능",
                    "주차 할 수",
                ],
                scope="pure",
                base_score=0.9,
            ),
        ],
    )

    # AMENITY_QUESTION
    rules[MessageIntent.AMENITY_QUESTION] = IntentRuleConfig(
        intent=MessageIntent.AMENITY_QUESTION,
        max_score=0.85,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "수건",
                    "타월",
                    "이불",
                    "이불이",
                    "침구",
                    "베개",
                    "칫솔",
                    "치약",
                    "샴푸",
                    "린스",
                    "바디워시",
                    "드라이기",
                    "드라이어",
                    "전자레인지",
                    "인덕션",
                    "취사",
                    "조리도구",
                    "와이파이",
                    "wifi",
                    "wi-fi",
                ],
                scope="both",
                base_score=0.85,
            ),
        ],
    )

    # THANKS_OR_GOOD_REVIEW
    rules[MessageIntent.THANKS_OR_GOOD_REVIEW] = IntentRuleConfig(
        intent=MessageIntent.THANKS_OR_GOOD_REVIEW,
        max_score=0.8,
        keyword_rules=[
            KeywordRule(
                keywords=[
                    "감사합니다",
                    "감사해요",
                    "고마워요",
                    "덕분에",
                    "잘 지냈",
                    "잘 머물렀",
                    "좋았어요",
                    "좋았습니다",
                    "추천 드",
                    "추천합니다",
                    "다음에 또",
                    "또 올게요",
                ],
                scope="pure",
                base_score=0.8,
            ),
        ],
    )

    return rules