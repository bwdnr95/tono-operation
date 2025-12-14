from __future__ import annotations

from typing import Optional

from app.domain.intents import MessageIntent, FineGrainedIntent
from app.domain.intents.auto_action import (
    MessageActionType,
    MessageActionDecision,
)


class IntentActionDecider:
    """
    MessageIntent + FineGrainedIntent + confidence를 바탕으로
    TONO가 어떤 액션을 취해야 하는지(action)를 결정하는 계층.

    MessageIntent는 실제 DB/서비스에서 쓰는 1차 Intent만 사용한다.
    (CHECKIN_QUESTION, RESERVATION_CHANGE, CANCELLATION, COMPLAINT, LOCATION_QUESTION, ...)
    """

    def decide(
        self,
        *,
        primary_intent: MessageIntent,
        fine_intent: Optional[FineGrainedIntent],
        intent_confidence: float,
        is_ambiguous: bool,
    ) -> MessageActionDecision:
        """
        가장 단순한 룰부터 시작해서, 운영하면서 점점 고도화할 수 있도록 설계.
        """

        # 1) Intent 신뢰도가 낮거나, 애매하다고 표시된 경우 → 직원 검토 위주
        if is_ambiguous or intent_confidence < 0.5:
            return MessageActionDecision(
                action=MessageActionType.STAFF_REVIEW_REQUIRED,
                reason=(
                    f"intent={primary_intent.name}, fine={getattr(fine_intent, 'name', None)}, "
                    f"confidence={intent_confidence:.2f}, ambiguous={is_ambiguous}"
                ),
                escalation_level=0,
                allow_auto_send=False,
                block_auto_reply=False,  # LLM 초안은 만들어도 됨
            )

        # 2) 클레임/민원 계열 → 직원 알림 + 수동 대응
        if primary_intent == MessageIntent.COMPLAINT:
            return MessageActionDecision(
                action=MessageActionType.STAFF_ALERT,
                reason="COMPLAINT intent → 즉시 직원 알림 필요",
                escalation_level=2,
                allow_auto_send=False,
                block_auto_reply=False,
            )

        # 3) 예약 변경/취소 계열 → 초안만 만들고 직원 검토 필수
        if primary_intent in {
            MessageIntent.RESERVATION_CHANGE,
            MessageIntent.CANCELLATION,
        }:
            return MessageActionDecision(
                action=MessageActionType.STAFF_REVIEW_REQUIRED,
                reason=f"{primary_intent.name} → 예약/취소 관련으로 사람 검토 필수",
                escalation_level=1,
                allow_auto_send=False,
                block_auto_reply=False,
            )

        # 4) 체크인/체크아웃/위치/편의시설/하우스룰/반려동물 계열 → 정책이 명확하면 자동응답 가능
        if primary_intent in {
            MessageIntent.CHECKIN_QUESTION,
            MessageIntent.CHECKOUT_QUESTION,
            MessageIntent.LOCATION_QUESTION,      # 주차 포함
            MessageIntent.AMENITY_QUESTION,
            MessageIntent.HOUSE_RULE_QUESTION,
            MessageIntent.PET_POLICY_QUESTION,
        }:
            return MessageActionDecision(
                action=MessageActionType.AUTO_REPLY,
                reason=f"{primary_intent.name} → 명확한 정보 제공성 문의, 자동응답 허용",
                escalation_level=0,
                allow_auto_send=True,
                block_auto_reply=False,
            )

        # 5) 인사/감사 등 → 자동응답 or 아무 것도 안 해도 됨
        if primary_intent == MessageIntent.THANKS_OR_GOOD_REVIEW:
            return MessageActionDecision(
                action=MessageActionType.NO_ACTION,
                reason="감사/긍정 피드백 메시지 → 굳이 답장 필요 없음",
                escalation_level=0,
                allow_auto_send=False,
                block_auto_reply=True,
            )

        # 6) 일반 문의 → 초안만 만들고 사람 검토
        if primary_intent == MessageIntent.GENERAL_QUESTION:
            return MessageActionDecision(
                action=MessageActionType.DRAFT_ONLY,
                reason="GENERAL_QUESTION → 초안만 만들고 사람 검토",
                escalation_level=0,
                allow_auto_send=False,
                block_auto_reply=False,
            )

        # 7) 기타 → 초안만 만들고 사람 검토
        return MessageActionDecision(
            action=MessageActionType.DRAFT_ONLY,
            reason=f"{primary_intent.name} (기타) → 초안만 만들고 사람 검토",
            escalation_level=0,
            allow_auto_send=False,
            block_auto_reply=False,
        )
