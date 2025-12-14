# backend/app/services/airbnb_intent_classifier.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.intents import (
    MessageIntent,
    MessageIntentResult,
    FineGrainedIntent,
    FineGrainedIntentResult,
)
from app.services.llm_intent_classifier import (
    classify_intent_with_llm_fine,
)


@dataclass(slots=True)
class HybridIntentResult:
    """
    TONO 내부에서 사용하는 Intent 분류 결과 래퍼.

    지금 버전은 사실상 "LLM-only" 이지만,
    나중에 rule 기반 FineGrainedIntentResult를 추가해도 시그니처를 안 바꾸기 위해
    HybridIntentResult 구조를 유지한다.
    """

    # 최종적으로 사용될 상위 Intent 결과 (MessageIntent 기준)
    message_result: MessageIntentResult

    # 최종 선택된 세분화 Intent 결과 (LLM 기준)
    fine_result: FineGrainedIntentResult

    # 향후 확장을 위한 필드 (현재는 None)
    rule_fine_result: Optional[FineGrainedIntentResult] = None
    llm_fine_result: Optional[FineGrainedIntentResult] = None

    # 디버깅용: 어떤 소스를 신뢰했는지
    source: str = "llm_only"  # "llm_only" | "rule_only" | "hybrid"


class AirbnbIntentClassifier:
    """
    Airbnb 게스트 메시지 Intent 분류기 (LLM 중심 설계).

    - pure_guest_message / subject / snippet 을 LLM에 전달
    - LLM은 FineGrainedIntent Enum에 정의된 값들 중에서만 선택
    - 결과를 MessageIntent / FineGrainedIntent 레벨로 반환

    현재 버전에서는 rule 기반 분류는 사용하지 않고,
    나중에 정말 확실한 패턴(예: Airbnb 시스템 알림 템플릿 등)에 한해서만
    fallback 용도로 추가할 수 있다.
    """

    def classify_airbnb_guest_intent(
        self,
        *,
        pure_guest_message: str,
        subject: str | None = None,
        snippet: str | None = None,
    ) -> HybridIntentResult:
        """
        Airbnb 게스트 free-text 메시지에 대한 Intent 분류.

        내부적으로는 llm_intent_classifier.classify_intent_with_llm_fine 을 호출해,
        FineGrainedIntentResult를 얻고, 이를 기반으로 MessageIntentResult를 구성한다.
        """

        # 1) LLM 기반 FineGrainedIntent 분류
        llm_result: FineGrainedIntentResult = classify_intent_with_llm_fine(
            pure_guest_message=pure_guest_message,
            subject=subject,
            snippet=snippet,
        )

        # 2) MessageIntentResult 구성
        #    - FineGrainedIntentResult 안에는 이미 primary_intent, confidence, reasons, is_ambiguous가 들어있음
        message_result = MessageIntentResult(
            intent=llm_result.primary_intent,
            confidence=llm_result.confidence,
            reasons=llm_result.reasons
            + [
                f"fine_intent={llm_result.fine_intent.value} "
                f"→ primary={llm_result.primary_intent.name}",
                "source=llm_only",
            ],
            is_ambiguous=llm_result.is_ambiguous,
        )

        return HybridIntentResult(
            message_result=message_result,
            fine_result=llm_result,
            rule_fine_result=None,
            llm_fine_result=llm_result,
            source="llm_only",
        )
