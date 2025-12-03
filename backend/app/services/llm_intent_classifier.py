from __future__ import annotations

import json
import os
from typing import List

from pydantic import BaseModel, ValidationError

from app.domain.intents import MessageIntent, MessageIntentResult

try:
    # 최신 openai 라이브러리 스타일 (pip install openai)
    from openai import OpenAI

    _openai_client: OpenAI | None = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    _openai_client = None


class LlmIntentRawResponse(BaseModel):
    intent: str
    confidence: float
    reasons: List[str]


def _map_intent_name(name: str) -> MessageIntent:
    """
    LLM이 반환한 intent 문자열을 MessageIntent Enum으로 매핑.

    - Enum 이름 그대로 주는 것을 권장 (예: PET_POLICY_QUESTION)
    - 혹시 한글/소문자 등을 반환해도 최대한 매핑 시도 후, 실패 시 OTHER 로 fallback
    """
    name = name.strip().upper()

    # Enum 이름 그대로 들어오는 happy path
    try:
        return MessageIntent[name]
    except KeyError:
        pass

    # 간단한 한글 매핑 예시 (필요시 확장)
    korean_map = {
        "체크인": MessageIntent.CHECKIN_QUESTION,
        "체크아웃": MessageIntent.CHECKOUT_QUESTION,
        "예약변경": MessageIntent.RESERVATION_CHANGE,
        "취소": MessageIntent.CANCELLATION,
        "불만": MessageIntent.COMPLAINT,
        "위치문의": MessageIntent.LOCATION_QUESTION,
        "편의시설문의": MessageIntent.AMENITY_QUESTION,
        "반려동물문의": MessageIntent.PET_POLICY_QUESTION,
        "일반문의": MessageIntent.GENERAL_QUESTION,
        "감사인사": MessageIntent.THANKS_OR_GOOD_REVIEW,
    }

    if name in korean_map:
        return korean_map[name]

    return MessageIntent.OTHER


def classify_intent_with_llm(
    *,
    pure_guest_message: str,
    subject: str | None = None,
    snippet: str | None = None,
) -> MessageIntentResult:
    """
    LLM을 사용하여 게스트 Intent 를 분류.

    - 입력: 순수 게스트 메시지 (필수), subject/snippet (선택)
    - 출력: MessageIntentResult
    """

    if _openai_client is None:
        # 환경에 LLM 클라이언트가 구성되지 않은 경우, OTHER 로 fallback
        return MessageIntentResult(
            intent=MessageIntent.OTHER,
            confidence=0.0,
            reasons=["LLM 클라이언트가 초기화되지 않아 OTHER 로 fallback"],
            is_ambiguous=True,
        )

    # 1) 프롬프트 구성
    system_prompt = """
당신은 TONO OPERATION의 Airbnb 게스트 메시지 분류 어시스턴트입니다.
게스트가 보낸 한국어/영어 메시지를 읽고, 아래 Intent 중 하나로 분류하세요.

가능한 Intent 목록 (MessageIntent Enum):

- CHECKIN_QUESTION: 체크인 시간/방법/입실 가능 여부에 대한 문의
- CHECKOUT_QUESTION: 체크아웃/퇴실 시간/방법 관련 문의
- RESERVATION_CHANGE: 날짜/인원/숙박일수 변경 요청
- CANCELLATION: 예약 취소/환불 관련 문의
- COMPLAINT: 시설/청소/소음/서비스 불만, 문제 제기
- LOCATION_QUESTION: 위치/길찾기/주차 관련 문의
- AMENITY_QUESTION: 수건/침구/비품/시설/와이파이 등 편의시설 관련 문의
- PET_POLICY_QUESTION: 반려동물 동반 가능 여부/조건/추가 비용 등에 대한 문의
- GENERAL_QUESTION: 위 카테고리에 명확히 들어가지 않는 일반 문의
- THANKS_OR_GOOD_REVIEW: 감사 인사, 숙박이 좋았다는 피드백
- OTHER: 위 어느 것에도 맞지 않을 때

반드시 JSON 형식으로만 답변하세요 (설명 문장 X):

{
  "intent": "<MessageIntent 이름 또는 한국어 간단 레이블>",
  "confidence": 0.0 ~ 1.0 사이의 숫자,
  "reasons": ["짧은 이유 1", "짧은 이유 2", ...]
}
""".strip()

    user_content_parts: List[str] = []

    if subject:
        user_content_parts.append(f"[제목]\n{subject}")
    if snippet:
        user_content_parts.append(f"[스니펫]\n{snippet}")

    user_content_parts.append(f"[게스트 순수 메시지]\n{pure_guest_message}")

    user_prompt = "\n\n".join(user_content_parts)

    # 2) LLM 호출
    completion = _openai_client.chat.completions.create(
        model=os.getenv("TONO_INTENT_MODEL", "gpt-4.1-mini"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    raw_text = completion.choices[0].message.content or ""

    # 3) JSON 파싱
    try:
        data = json.loads(raw_text)
        parsed = LlmIntentRawResponse(**data)
    except (json.JSONDecodeError, ValidationError):
        # 파싱 실패 시 OTHER 로 fallback
        return MessageIntentResult(
            intent=MessageIntent.OTHER,
            confidence=0.3,
            reasons=[
                "LLM 응답 JSON 파싱 실패",
                f"raw: {raw_text[:200]}...",
            ],
            is_ambiguous=True,
        )

    mapped_intent = _map_intent_name(parsed.intent)

    return MessageIntentResult(
        intent=mapped_intent,
        confidence=max(0.0, min(parsed.confidence, 1.0)),
        reasons=parsed.reasons + [f"LLM 예측 intent={parsed.intent} -> {mapped_intent.name}"],
        is_ambiguous=False,  # 애매 여부는 상위 오케스트레이터에서 다시 판단
    )