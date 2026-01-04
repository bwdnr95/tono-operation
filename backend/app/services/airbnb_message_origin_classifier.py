import re
from typing import Optional

from app.domain.intents import (
    MessageActor,
    MessageActionability,
    AirbnbMessageOriginResult,
)

ROLE_HOST_PATTERNS = [
    r"\n\s*호스트\s*\n",  # 줄 단위로 '호스트' 라벨이 있는 경우
    r"\n\s*공동\s*호스트\s*\n",  # 줄 단위로 '공동 호스트' 라벨이 있는 경우
]
ROLE_GUEST_PATTERNS = [
    r"\n\s*게스트\s*\n",  # 줄 단위로 '게스트' 라벨이 있는 경우 (예상 패턴)
]

# 시스템/마케팅성 문구 (예시, 추후 실제 샘플 보면서 계속 추가)
SYSTEM_KEYWORDS = [
    "예약이 확정되었습니다",
    "예약이 취소되었습니다",
    "리뷰를 남겨보세요",
    "리뷰를 남기실래요",
    "체크인까지 남은 시간",
    "새로운 알림",
]


def _search_patterns(text: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False


def _detect_role_label_from_text(text: str) -> Optional[str]:
    """
    Airbnb 이메일 텍스트에서 '호스트' / '게스트' 역할 라벨을 감지.
    예시:
        낭그늘
        (공백)
        호스트
        (공백)
        Tarshay님, 안녕하세요...
    """
    if _search_patterns(text, ROLE_HOST_PATTERNS):
        return "호스트"
    if _search_patterns(text, ROLE_GUEST_PATTERNS):
        return "게스트"
    return None


def _looks_like_system_notification(text: str, subject: str | None) -> bool:
    haystack = (subject or "") + "\n" + text
    return any(keyword in haystack for keyword in SYSTEM_KEYWORDS)


def classify_airbnb_message_origin(
    *,
    decoded_text_body: str,
    decoded_html_body: str | None = None,  # 필요시 향후 사용
    subject: str | None = None,
    snippet: str | None = None,
    sender_role: str | None = None,  # 🔹 파싱 단계에서 이미 분류된 역할 (예약자/게스트/호스트)
) -> AirbnbMessageOriginResult:
    """
    Airbnb에서 온 이메일이
    - 누가 보낸 것인지 (게스트/호스트/시스템)
    - TONO가 답변해야 하는지
    를 1차 Rule 기반으로 판별.

    이 함수는 'Intent 분석' 이전 단계에서 호출되어,
    게스트 메시지가 맞는 경우에만 Intent 분석기로 넘기는 역할을 한다.
    
    sender_role이 이미 제공된 경우 (파싱 단계에서 분리된 메시지),
    해당 값을 우선 사용한다.
    """

    text = decoded_text_body or ""
    
    # 🔹 sender_role이 이미 제공된 경우 우선 사용
    if sender_role:
        if sender_role == "호스트":
            return AirbnbMessageOriginResult(
                actor=MessageActor.HOST,
                actionability=MessageActionability.OUTGOING_COPY,
                confidence=0.95,
                reasons=[f"파싱 단계에서 '{sender_role}' 역할로 분류됨"],
                raw_role_label=sender_role,
            )
        elif sender_role in ("예약자", "게스트"):
            return AirbnbMessageOriginResult(
                actor=MessageActor.GUEST,
                actionability=MessageActionability.NEEDS_REPLY,
                confidence=0.95,
                reasons=[f"파싱 단계에서 '{sender_role}' 역할로 분류됨"],
                raw_role_label=sender_role,
            )
    
    # 🔹 sender_role이 없는 경우 기존 로직 수행
    role_label = _detect_role_label_from_text(text)

    # 1) 시스템 알림/마케팅 메일인지 먼저 확인
    if _looks_like_system_notification(text, subject):
        return AirbnbMessageOriginResult(
            actor=MessageActor.SYSTEM,
            actionability=MessageActionability.SYSTEM_NOTIFICATION,
            confidence=0.9,
            reasons=["예약/리뷰/알림 등 시스템 키워드 패턴 매칭"],
            raw_role_label=role_label,
        )

    # 2) 호스트/게스트 라벨 기반 판단
    if role_label == "호스트":
        # 이 경우는 "호스트가 손님에게 보낸 메시지의 사본"일 가능성이 매우 높다.
        return AirbnbMessageOriginResult(
            actor=MessageActor.HOST,
            actionability=MessageActionability.OUTGOING_COPY,
            confidence=0.9,
            reasons=["본문 상단에 '호스트' 라벨이 감지됨 → 우리가 보낸 메시지 사본으로 판단"],
            raw_role_label=role_label,
        )

    if role_label == "게스트":
        # 게스트가 보낸 메시지라면, 기본적으로는 "답변이 필요한 메시지"로 간주한다.
        # (향후, 단순 '감사인사', '좋아요/이모지' 등은 예외 rule 추가)
        return AirbnbMessageOriginResult(
            actor=MessageActor.GUEST,
            actionability=MessageActionability.NEEDS_REPLY,
            confidence=0.9,
            reasons=["본문 상단에 '게스트' 라벨이 감지됨 → 게스트 메시지로 판단"],
            raw_role_label=role_label,
        )

    # 3) 라벨이 없는 경우: 향후 샘플 쌓이면서 rule 보강 or ML 도입
    #    지금은 보수적으로 UNKNOWN + FYI 로 둔다.
    return AirbnbMessageOriginResult(
        actor=MessageActor.UNKNOWN,
        actionability=MessageActionability.FYI,
        confidence=0.3,
        reasons=["'호스트' / '게스트' 역할 라벨 패턴이 감지되지 않음"],
        raw_role_label=role_label,
    )