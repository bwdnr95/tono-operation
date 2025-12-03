from __future__ import annotations

from typing import Dict, List, Tuple

from app.domain.intents import MessageIntent, MessageIntentResult
from app.domain.intents.keyword_rules import (
    IntentRuleConfig,
    KeywordRule,
    get_default_intent_rules,
)
from app.services.airbnb_guest_message_extractor import (
    extract_guest_message_segment,
)
from app.services.llm_intent_classifier import (
    classify_intent_with_llm,
)


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(kw in text for kw in keywords)


def _matches_rule(
    rule: KeywordRule,
    *,
    pure_text: str,
    full_text: str,
) -> bool:
    if rule.scope == "pure":
        target_text = pure_text
    elif rule.scope == "full":
        target_text = full_text
    else:
        target_text = pure_text + "\n" + full_text

    if rule.requires:
        if not all(req in target_text for req in rule.requires):
            return False

    if rule.negatives:
        if any(neg in target_text for neg in rule.negatives):
            return False

    return _contains_any(target_text, rule.keywords)


def _score_intents_with_rules(
    *,
    rules: Dict[MessageIntent, IntentRuleConfig],
    pure_text: str,
    full_text: str,
    reasons: List[str],
) -> Dict[MessageIntent, float]:
    scores: Dict[MessageIntent, float] = {}

    for intent, cfg in rules.items():
        intent_score = 0.0

        for rule in cfg.keyword_rules:
            if _matches_rule(rule, pure_text=pure_text, full_text=full_text):
                intent_score = max(intent_score, rule.base_score)
                reasons.append(
                    f"{intent.name}: scope={rule.scope} 룰에서 키워드 매칭 (base_score={rule.base_score})"
                )

        if intent_score > 0:
            scores[intent] = min(intent_score, cfg.max_score)

    return scores


def _classify_with_rules_only(
    *,
    decoded_text_body: str,
    subject: str | None,
    snippet: str | None,
) -> MessageIntentResult:
    """
    순수 룰 기반 Intent 분류 (LLM 미사용).
    기존 TONO Intent 엔진 V2의 로직이 여기에 포함됨.
    """

    pure_guest_message = extract_guest_message_segment(decoded_text_body) or ""
    pure_text = _normalize_text(pure_guest_message)

    subj = _normalize_text(subject)
    snip = _normalize_text(snippet)
    full_text = "\n".join(filter(None, [subj, snip, _normalize_text(decoded_text_body)]))

    rules = get_default_intent_rules()
    reasons: List[str] = []

    scores = _score_intents_with_rules(
        rules=rules,
        pure_text=pure_text,
        full_text=full_text,
        reasons=reasons,
    )

    if not scores:
        if "?" in pure_text or "인가요" in pure_text or "일까요" in pure_text:
            return MessageIntentResult(
                intent=MessageIntent.GENERAL_QUESTION,
                confidence=0.5,
                reasons=reasons + ["질문 표현은 있으나 특정 Intent 룰이 매칭되지 않음 (rules-only)"],
                is_ambiguous=True,
            )
        return MessageIntentResult(
            intent=MessageIntent.OTHER,
            confidence=0.3,
            reasons=reasons + ["명확한 Intent 룰이 매칭되지 않음 (rules-only)"],
            is_ambiguous=True,
        )

    sorted_items: List[Tuple[MessageIntent, float]] = sorted(
        scores.items(), key=lambda kv: kv[1], reverse=True
    )
    top_intent, top_score = sorted_items[0]

    is_ambiguous = False
    secondary_intent = None
    secondary_confidence = None

    if len(sorted_items) > 1:
        second_intent, second_score = sorted_items[1]
        if (top_score - second_score) <= 0.15:
            is_ambiguous = True
            secondary_intent = second_intent
            secondary_confidence = second_score
            reasons.append(
                f"두 가지 Intent({top_intent.name}, {second_intent.name})가 비슷한 점수로 감지됨 (rules-only)"
            )

    return MessageIntentResult(
        intent=top_intent,
        confidence=top_score,
        reasons=reasons,
        is_ambiguous=is_ambiguous,
        secondary_intent=secondary_intent,
        secondary_confidence=secondary_confidence,
    )


def classify_airbnb_guest_intent(
    *,
    decoded_text_body: str,
    subject: str | None = None,
    snippet: str | None = None,
    use_llm_fallback: bool = True,
    rule_confidence_strict_threshold: float = 0.85,
    rule_confidence_loose_threshold: float = 0.6,
) -> MessageIntentResult:
    """
    TONO 최종 Intent 분류기 (룰 + LLM 하이브리드).

    1) 먼저 룰 기반 분류를 수행
    2) 룰 결과가 충분히 확실하면 그대로 사용
    3) 룰 결과가 애매하거나, GENERAL/OTHER 쪽이면 LLM을 호출하여 보완
    4) 룰과 LLM 결과를 비교하여 최종 Intent 결정

    - use_llm_fallback=False 로 호출하면 기존 rules-only 동작을 유지 가능
    """

    # 1) 룰 기반 분류
    rule_result = _classify_with_rules_only(
        decoded_text_body=decoded_text_body,
        subject=subject,
        snippet=snippet,
    )

    # 2) 룰 결과가 매우 확실하면 그대로 반환
    if not use_llm_fallback:
        return rule_result

    if (
        rule_result.intent not in (MessageIntent.GENERAL_QUESTION, MessageIntent.OTHER)
        and rule_result.confidence >= rule_confidence_strict_threshold
        and not rule_result.is_ambiguous
    ):
        # 확실한 룰 결과 → LLM 불필요
        rule_result.reasons.append("룰 기반 결과가 충분히 확실하여 LLM 호출을 생략")
        return rule_result

    # 3) LLM 호출 (순수 게스트 메시지 기준)
    pure_guest_message = extract_guest_message_segment(decoded_text_body) or ""
    llm_result = classify_intent_with_llm(
        pure_guest_message=pure_guest_message,
        subject=subject,
        snippet=snippet,
    )

    # 4) 룰 + LLM 결과 병합 전략

    # 4-1. 룰이 너무 약하고(GENERAL/OTHER), LLM이 높은 confidence를 주면 LLM 우선
    if rule_result.intent in (MessageIntent.GENERAL_QUESTION, MessageIntent.OTHER):
        if llm_result.confidence >= rule_confidence_loose_threshold:
            llm_result.reasons.extend(
                [
                    f"룰 결과={rule_result.intent.name}, conf={rule_result.confidence:.2f} → "
                    "LLM 결과가 더 신뢰도 높아 LLM 결과 채택",
                ]
            )
            return llm_result

    # 4-2. 둘 다 특정 Intent를 내놨을 때, 더 높은 confidence 를 채택
    if llm_result.intent != MessageIntent.OTHER and (
        llm_result.confidence > rule_result.confidence + 0.1
    ):
        # LLM이 상당히 더 확신하는 경우
        merged_reasons = (
            rule_result.reasons
            + ["룰 결과보다 LLM confidence가 충분히 높아 LLM Intent 채택"]
            + llm_result.reasons
        )
        return MessageIntentResult(
            intent=llm_result.intent,
            confidence=llm_result.confidence,
            reasons=merged_reasons,
            is_ambiguous=False,
            secondary_intent=rule_result.intent,
            secondary_confidence=rule_result.confidence,
        )

    # 4-3. 그 외의 경우: 룰 결과를 기본으로, LLM 정보를 참고 정보로만 사용
    merged_reasons = rule_result.reasons + [
        f"LLM 보조 결과: intent={llm_result.intent.name}, "
        f"conf={llm_result.confidence:.2f}",
    ] + llm_result.reasons

    return MessageIntentResult(
        intent=rule_result.intent,
        confidence=rule_result.confidence,
        reasons=merged_reasons,
        is_ambiguous=rule_result.is_ambiguous,
        secondary_intent=llm_result.intent,
        secondary_confidence=llm_result.confidence,
    )