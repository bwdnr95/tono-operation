# backend/app/services/auto_reply_recommendation_service.py

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.domain.models.auto_reply_template import AutoReplyTemplate
from app.domain.models.auto_reply_recommendation import AutoReplyRecommendation
from app.repositories.auto_reply_template_repository import AutoReplyTemplateRepository
from app.domain.models.incoming_message import IncomingMessage


class AutoReplyRecommendationService:
    """
    Intent + pure_guest_message 기반 자동응답 추천 엔진 (sync Session 기반).

    - Session 은 sync 이므로, 내부에서 절대 await 사용하지 않는다.
    - 다만 라우터 호환을 위해 public 메서드는 async def 로 노출할 수 있다.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.template_repo = AutoReplyTemplateRepository(session)

    async def recommend_for_message(
        self,
        message: IncomingMessage,
        *,
        max_results: int = 3,
    ) -> List[AutoReplyRecommendation]:
        """
        단일 메시지에 대한 자동응답 추천.

        NOTE:
        - async def 이지만, 내부는 전부 sync 호출이다.
        - 이 함수는 await 없이 써도 되지만,
          기존 FastAPI 라우터 패턴을 맞추기 위해 async 로 정의해둔 것.
        """

        if message.intent is None:
            # Intent 없는 메시지는 추천 안 함
            return []

        intent_code = (
            message.intent.value if hasattr(message.intent, "value") else message.intent
        )
        locale = getattr(message, "locale", None) or "ko-KR"
        channel = getattr(message, "channel", None) or "airbnb"
        property_code = getattr(message, "property_code", None)
        intent_confidence = float(getattr(message, "intent_confidence", 0.0) or 0.0)

        candidates: List[AutoReplyTemplate] = []

        # 1) property + channel + locale
        if property_code:
            candidates = self.template_repo.list_by_filters(
                intent=intent_code,
                locale=locale,
                channel=channel,
                property_code=property_code,
            )

        # 2) property 없는 글로벌 템플릿
        if not candidates:
            candidates = self.template_repo.list_by_filters(
                intent=intent_code,
                locale=locale,
                channel=channel,
                property_code=None,
            )

        # 3) generic 채널 fallback
        if not candidates:
            candidates = self.template_repo.list_by_filters(
                intent=intent_code,
                locale=locale,
                channel="generic",
                property_code=None,
            )

        if not candidates:
            return []

        # min_intent_confidence 필터
        filtered = [
            t
            for t in candidates
            if self._passes_confidence_filter(t, intent_confidence)
        ]

        if not filtered:
            return []

        # 스코어 계산 & 추천 DTO 생성
        recommendations: List[AutoReplyRecommendation] = [
            self._build_recommendation(
                template=t,
                message=message,
                intent_confidence=intent_confidence,
            )
            for t in filtered
        ]

        # score 기준 정렬 후 자르기
        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations[:max_results]

    @staticmethod
    def _passes_confidence_filter(
        template: AutoReplyTemplate,
        intent_confidence: float,
    ) -> bool:
        """
        템플릿 min/max_intent_confidence 조건 체크.
        """
        if template.min_intent_confidence is not None:
            if intent_confidence < template.min_intent_confidence:
                return False

        if template.max_intent_confidence is not None:
            if intent_confidence > template.max_intent_confidence:
                return False

        return True

    def _build_recommendation(
        self,
        *,
        template: AutoReplyTemplate,
        message: IncomingMessage,
        intent_confidence: float,
    ) -> AutoReplyRecommendation:
        """
        템플릿 + 메시지 컨텍스트 → 추천 DTO.
        (1차 버전: placeholder 실제 치환은 아직 안 함)
        """

        priority_factor = max(0, 100 - template.priority) / 100.0  # 0~1

        # 간단한 score: intent_confidence(70%) + priority_factor(30%)
        score = intent_confidence * 0.7 + priority_factor * 0.3

        auto_send_suggested = False
        if template.auto_send_enabled:
            max_conf = template.auto_send_max_confidence or 1.0
            if intent_confidence <= max_conf:
                auto_send_suggested = True

        reason_parts = [
            f"intent={message.intent}",
            f"intent_confidence={intent_confidence:.2f}",
            f"template_priority={template.priority}",
        ]
        if template.min_intent_confidence is not None:
            reason_parts.append(f"min_conf={template.min_intent_confidence:.2f}")
        if template.auto_send_enabled:
            reason_parts.append("auto_send_enabled=True")

        reason = "; ".join(reason_parts)

        return AutoReplyRecommendation(
            template_id=template.id,
            intent=template.intent,
            locale=template.locale,
            channel=template.channel,
            name=template.name,
            preview_subject=template.subject_template,
            preview_body=template.body_template,
            score=score,
            auto_send_suggested=auto_send_suggested,
            reason=reason,
        )
