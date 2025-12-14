# backend/app/services/llm_intent_classifier.py

from __future__ import annotations

import json
import logging
from typing import List, Optional

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.domain.intents import (
    MessageIntent,
    MessageIntentResult,
    FineGrainedIntent,
    FineGrainedIntentResult,
    map_fine_to_primary_intent,
)

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# OpenAI / LLM 클라이언트 초기화
#   - TONO 공통 settings(LLM_API_KEY, LLM_MODEL) 사용
# -------------------------------------------------------------------

try:
    from openai import OpenAI  # openai>=1.0 스타일

    if settings.LLM_API_KEY:
        _openai_client: Optional[OpenAI] = OpenAI(api_key=settings.LLM_API_KEY)
        _HAS_OPENAI_CLIENT = True
    else:
        _openai_client = None
        _HAS_OPENAI_CLIENT = False
        logger.warning(
            "LLM_INTENT: LLM_API_KEY not set in settings; LLM intent classifier disabled."
        )
except Exception:  # pragma: no cover - 라이브러리 미설치 등
    _openai_client = None
    _HAS_OPENAI_CLIENT = False
    logger.warning(
        "LLM_INTENT: OpenAI client initialization failed; LLM intent classifier disabled."
    )


# -------------------------------------------------------------------
# LLM 응답 스키마 (raw JSON)
# -------------------------------------------------------------------


class LlmIntentRawResponse(BaseModel):
    """
    LLM이 반환하는 '세분화 Intent' JSON 형식.

    예시:

    {
      "fine_intent": "EARLY_CHECKIN_REQUEST",
      "confidence": 0.92,
      "reasons": [
        "게스트가 일반 체크인 시간보다 일찍 들어가고 싶다는 표현",
        "날짜/시간과 함께 '얼리 체크인'이라는 단어 사용"
      ]
    }
    """

    fine_intent: str
    confidence: float
    reasons: List[str]


# -------------------------------------------------------------------
# FineGrainedIntent 이름 파싱 유틸 (LLM이 살짝 다르게 말해도 수습)
# -------------------------------------------------------------------


def _parse_fine_intent_name(name: str | None) -> Optional[FineGrainedIntent]:
    """
    LLM이 준 fine_intent 문자열을 FineGrainedIntent Enum으로 변환.
    - 이름/값/alias까지 최대한 유연하게 매핑.
    """

    if not name:
        return None

    normalized = name.strip().upper()

    # Alias 맵 (LLM이 대충 말했을 때 보정용)
    alias_map: dict[str, FineGrainedIntent] = {
        # 체크인
        "CHECKIN_TIME": FineGrainedIntent.CHECKIN_TIME_QUESTION,
        "CHECK_IN_TIME": FineGrainedIntent.CHECKIN_TIME_QUESTION,
        "EARLY_CHECKIN": FineGrainedIntent.EARLY_CHECKIN_REQUEST,
        "EARLY_CHECK_IN": FineGrainedIntent.EARLY_CHECKIN_REQUEST,
        "LATE_CHECKIN": FineGrainedIntent.LATE_CHECKIN_REQUEST,
        "LATE_CHECK_IN": FineGrainedIntent.LATE_CHECKIN_REQUEST,
        # 체크아웃
        "CHECKOUT_TIME": FineGrainedIntent.CHECKOUT_TIME_QUESTION,
        "CHECK_OUT_TIME": FineGrainedIntent.CHECKOUT_TIME_QUESTION,
        "LATE_CHECKOUT": FineGrainedIntent.LATE_CHECKOUT_REQUEST,
        "LATE_CHECK_OUT": FineGrainedIntent.LATE_CHECKOUT_REQUEST,
        # 취소/정책
        "CANCELLATION": FineGrainedIntent.CANCELLATION_REQUEST,
        "CANCEL_REQUEST": FineGrainedIntent.CANCELLATION_REQUEST,
        "CANCEL": FineGrainedIntent.CANCELLATION_REQUEST,
        "CANCELLATION_POLICY": FineGrainedIntent.CANCELLATION_POLICY_QUESTION,
        # 편의시설
        "PARKING": FineGrainedIntent.PARKING_QUESTION,
        "WIFI": FineGrainedIntent.WIFI_QUESTION,
        "WI_FI": FineGrainedIntent.WIFI_QUESTION,
        "KITCHEN": FineGrainedIntent.KITCHEN_EQUIPMENT_QUESTION,
        "LAUNDRY": FineGrainedIntent.LAUNDRY_QUESTION,
        # 반려동물/흡연
        "PET": FineGrainedIntent.PET_ALLOWED_QUESTION,
        "PET_POLICY": FineGrainedIntent.PET_ALLOWED_QUESTION,
        "SMOKING": FineGrainedIntent.HOUSE_RULE_SMOKING_QUESTION,
        # 인사/감사
        "GREETING": FineGrainedIntent.GENERAL_GREETING,
        "THANKS": FineGrainedIntent.GENERAL_THANKS,
    }

    # 1) alias 우선
    if normalized in alias_map:
        return alias_map[normalized]

    # 2) Enum 이름 직접 매칭 시도
    try:
        return FineGrainedIntent[normalized]
    except KeyError:
        # 3) 값 기반 매칭 (e.g. "EARLY_CHECKIN_REQUEST")
        for fi in FineGrainedIntent:
            if fi.value.upper() == normalized:
                return fi

    return None


# -------------------------------------------------------------------
# 내부 유틸: LLM 호출 (raw JSON → Pydantic 변환)
# -------------------------------------------------------------------


def _call_llm_for_intent(
    *,
    pure_guest_message: str,
    subject: str | None = None,
    snippet: str | None = None,
) -> Optional[LlmIntentRawResponse]:
    """
    LLM에 게스트 메시지를 보내 Intent 추론을 요청.
    - 성공 시 LlmIntentRawResponse 반환
    - 실패 시 None 반환 (상위에서 안전하게 fallback)

    병욱님 환경의 openai 버전 호환을 위해:
      1) Responses API + response_format (최신 방식) 시도
      2) TypeError('response_format') 발생 시 → chat.completions 방식으로 자동 fallback
    """

    if not _HAS_OPENAI_CLIENT or _openai_client is None:
        logger.warning("LLM_INTENT: OpenAI client not available; skip LLM intent.")
        return None

    model_name = settings.LLM_MODEL or "gpt-4.1-mini"

    allowed_intents = [fi.name for fi in FineGrainedIntent]

    system_prompt = (
        "You are an assistant for classifying guest messages for a vacation rental host.\n"
        "Your task is to choose the single MOST relevant fine-grained intent from the allowed list.\n"
        "Only choose from the allowed intents. Do NOT invent new labels.\n"
        "\n"
        "Return STRICT JSON with keys:\n"
        "  - fine_intent: string, one of the allowed intent names.\n"
        "  - confidence: float between 0 and 1.\n"
        "  - reasons: array of short Korean strings explaining why.\n"
        "\n"
        "If the message is unclear or doesn't match well, use OTHER with low confidence.\n"
    )

    payload = {
        "allowed_fine_intents": allowed_intents,
        "subject": subject,
        "snippet": snippet,
        "guest_message": pure_guest_message,
    }
    payload_text = json.dumps(payload, ensure_ascii=False)

    try:
        # -------------------------------------------------
        # 1) 최신 openai Responses API + json_object 시도
        # -------------------------------------------------
        try:
            resp = _openai_client.responses.create(
                model=model_name,
                input=[
                    {"type": "input_text", "text": system_prompt},
                    {"type": "input_text", "text": payload_text},
                ],
                response_format={"type": "json_object"},
            )

            try:
                text = resp.output[0].content[0].text
            except Exception as e:  # pragma: no cover
                logger.error("LLM_INTENT: Unexpected Responses API structure: %r", resp)
                raise e

        except TypeError as te:
            # 병욱님 환경처럼 response_format을 지원 안 하는 버전일 때:
            # → chat.completions로 자동 fallback
            if "response_format" not in str(te):
                raise

            logger.info(
                "LLM_INTENT: Responses.create does not support response_format; "
                "falling back to chat.completions."
            )

            chat_resp = _openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "다음 JSON 컨텍스트를 참고하여, "
                            "설명된 스키마에 맞는 JSON만 반환해 주세요.\n"
                            f"JSON:\n{payload_text}"
                        ),
                    },
                ],
            )
            text = chat_resp.choices[0].message.content

        # -------------------------------------------------
        # 2) 공통: text(문자열)를 JSON으로 파싱 + 검증
        # -------------------------------------------------
        raw_dict = json.loads(text)
        raw = LlmIntentRawResponse.model_validate(raw_dict)
        return raw

    except ValidationError as ve:
        logger.warning("LLM_INTENT: JSON validation error: %s", ve)
        return None
    except json.JSONDecodeError as je:
        logger.warning("LLM_INTENT: JSON decode error: %s | text=%r", je, locals().get("text"))
        return None
    except Exception as exc:  # pragma: no cover - 네트워크/기타 예외
        logger.warning("LLM_INTENT: OpenAI call failed: %s", exc)
        return None


# -------------------------------------------------------------------
# Public API 1: Primary MessageIntent만 리턴
# -------------------------------------------------------------------


def classify_intent_with_llm(
    *,
    pure_guest_message: str,
    subject: str | None = None,
    snippet: str | None = None,
) -> MessageIntentResult:
    """
    LLM 기반 Intent 분류 (Primary MessageIntent 레벨까지).

    내부적으로:
      1) LLM → FineGrainedIntent 추론
      2) FineGrainedIntent → MessageIntent 로 매핑
    """

    fine_result = classify_intent_with_llm_fine(
        pure_guest_message=pure_guest_message,
        subject=subject,
        snippet=snippet,
    )

    # MessageIntentResult는 TONO 전역에서 사용하는 상위 Intent 결과
    return MessageIntentResult(
        intent=fine_result.primary_intent,
        confidence=fine_result.confidence,
        reasons=fine_result.reasons
        + [
            f"fine_intent={fine_result.fine_intent.value} "
            f"→ primary={fine_result.primary_intent.name}"
        ],
        is_ambiguous=fine_result.is_ambiguous,
    )


# -------------------------------------------------------------------
# Public API 2: 세분화 Intent까지 리턴 (AirbnbIntentClassifier에서 사용)
# -------------------------------------------------------------------


def classify_intent_with_llm_fine(
    *,
    pure_guest_message: str,
    subject: str | None = None,
    snippet: str | None = None,
) -> FineGrainedIntentResult:
    """
    LLM 기반 FineGrainedIntent 분류.

    - 반환: FineGrainedIntentResult
      - fine_intent: 세분화 Intent
      - primary_intent: map_fine_to_primary_intent(fine_intent)
      - confidence: 0 ~ 1
      - reasons: List[str]
      - is_ambiguous: MessageIntent.OTHER 등 애매한 경우 True
    """

    raw = _call_llm_for_intent(
        pure_guest_message=pure_guest_message,
        subject=subject,
        snippet=snippet,
    )

    if raw is None:
        # LLM 사용 불가 or 실패 → OTHER 로 안전 fallback
        return FineGrainedIntentResult(
            fine_intent=FineGrainedIntent.OTHER,
            primary_intent=MessageIntent.OTHER,
            confidence=0.2,
            reasons=["LLM 사용 불가 또는 JSON 파싱 실패로 인한 기본 fallback"],
            is_ambiguous=True,
        )

    fine_enum = _parse_fine_intent_name(raw.fine_intent)
    if fine_enum is None:
        fine_enum = FineGrainedIntent.OTHER

    primary = map_fine_to_primary_intent(fine_enum)

    # confidence는 0~1 범위로 클램프
    confidence = max(0.0, min(raw.confidence, 1.0))

    # primary가 OTHER로 매핑되면 모호한 케이스로 간주
    is_ambiguous = primary == MessageIntent.OTHER or confidence < 0.5

    return FineGrainedIntentResult(
        fine_intent=fine_enum,
        primary_intent=primary,
        confidence=confidence,
        reasons=raw.reasons,
        is_ambiguous=is_ambiguous,
    )
