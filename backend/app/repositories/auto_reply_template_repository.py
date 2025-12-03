# backend/app/repositories/auto_reply_templates_repository.py

from __future__ import annotations

from typing import List, Optional, Union

from sqlalchemy.orm import Session

from app.domain.models.auto_reply_template import AutoReplyTemplate
from app.domain.intents import MessageIntent  # TONO Intent Enum


IntentLike = Union[MessageIntent, str]


def _normalize_intent(intent: IntentLike) -> str:
    """
    DB에 저장된 intent는 String 컬럼이므로,
    Python 쪽에서 넘어온 Enum/str 을 일관되게 문자열로 맞춰준다.

    - MessageIntent Enum 이면 .name 사용 (예: GENERAL_QUESTION)
    - 이미 문자열이면 그대로 사용
    """
    if isinstance(intent, MessageIntent):
        # TONO 설계 상 DB에는 "CHECKIN_QUESTION" 같은 코드 문자열을 저장한다고 가정
        return intent.name
    return str(intent)


class AutoReplyTemplateRepository:
    """
    auto_reply_templates 테이블용 레포지토리 (sync Session 기반).
    """

    def __init__(self, session: Session):
        self.session = session

    def get_best_template_for_intent(
        self,
        *,
        intent: IntentLike,
        locale: str = "ko",
    ) -> Optional[AutoReplyTemplate]:
        """
        Intent + locale 기준으로 가장 적합한 템플릿 한 개를 반환.

        - intent 파라미터는 Enum 또는 str 둘 다 허용
        - 내부에서는 항상 문자열로 정규화해서 비교
        """
        intent_value = _normalize_intent(intent)

        q = (
            self.session.query(AutoReplyTemplate)
            .filter(
                AutoReplyTemplate.intent == intent_value,
                AutoReplyTemplate.locale == locale,
                AutoReplyTemplate.is_active.is_(True),
            )
            .order_by(
                AutoReplyTemplate.priority.asc(),  # 숫자 작을수록 우선순위 높게
                AutoReplyTemplate.id.asc(),
            )
        )
        return q.first()

    def list_by_filters(
        self,
        *,
        intent: IntentLike,
        locale: Optional[str] = None,
        channel: Optional[str] = None,
        property_code: Optional[str] = None,
        is_active: bool = True,
    ) -> List[AutoReplyTemplate]:
        """
        Intent 기반 추천 엔진에서 사용하는 복수 템플릿 조회용 메서드.

        - sync Session 기반, 절대 await 하지 말 것.
        - priority 오름차순으로 정렬해서 반환.
        """
        intent_value = _normalize_intent(intent)

        q = self.session.query(AutoReplyTemplate).filter(
            AutoReplyTemplate.intent == intent_value,
        )

        if is_active is not None:
            q = q.filter(AutoReplyTemplate.is_active.is_(is_active))

        if locale is not None:
            q = q.filter(AutoReplyTemplate.locale == locale)

        if channel is not None:
            q = q.filter(AutoReplyTemplate.channel == channel)

        if property_code is not None:
            q = q.filter(AutoReplyTemplate.property_code == property_code)

        q = q.order_by(AutoReplyTemplate.priority.asc(), AutoReplyTemplate.id.asc())

        return q.all()
