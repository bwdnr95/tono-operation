# backend/app/repositories/auto_reply_template_repository.py

from __future__ import annotations

from typing import List, Optional, Union

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.domain.models.auto_reply_template import AutoReplyTemplate
from app.domain.intents import MessageIntent, FineGrainedIntent  # TONO Intent Enums

IntentLike = Union[MessageIntent, str]
FineIntentLike = Union[FineGrainedIntent, str]


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


def _normalize_fine_intent(fine_intent: Optional[FineIntentLike]) -> Optional[str]:
    """
    DB의 fine_intent 컬럼과 비교하기 위해 Enum/str 을 문자열로 맞춰준다.
    - FineGrainedIntent Enum 이면 .name 사용
    - None 이면 그대로 None
    """
    if fine_intent is None:
        return None
    if isinstance(fine_intent, FineGrainedIntent):
        return fine_intent.name
    return str(fine_intent)


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
        channel: Optional[str] = None,
        property_code: Optional[str] = None,
        fine_intent: Optional[FineIntentLike] = None,
        intent_confidence: Optional[float] = None,
    ) -> Optional[AutoReplyTemplate]:
        """
        Intent + (FineIntent) + locale + channel + property_code + confidence 범위를
        종합적으로 고려하여 가장 적합한 템플릿 1개를 반환한다.

        우선순위 정책:
          1) property_code 가 일치하는 템플릿이 NULL 보다 우선
          2) fine_intent 가 일치하는 템플릿이 NULL 보다 우선
          3) min_intent_confidence / max_intent_confidence 범위 안에 드는 템플릿만 사용
          4) priority (숫자 작을수록 우선) → id 순으로 결정

        - intent: MessageIntent Enum 또는 문자열
        - fine_intent: FineGrainedIntent Enum 또는 문자열 또는 None
        - locale: 기본 'ko'
        - channel: 예) 'airbnb', 'kakao' 등 (None이면 필터하지 않음)
        - property_code: 예) 'PV-A', 'PV-B' (None이면 글로벌 템플릿만)
        - intent_confidence: Intent 분류 신뢰도 (없으면 confidence 범위 필터 미적용)
        """
        intent_value = _normalize_intent(intent)
        fine_intent_value = _normalize_fine_intent(fine_intent)

        q = self.session.query(AutoReplyTemplate).filter(
            AutoReplyTemplate.intent == intent_value,
            AutoReplyTemplate.locale == locale,
            AutoReplyTemplate.is_active.is_(True),
        )

        # 채널 필터
        if channel is not None:
            q = q.filter(AutoReplyTemplate.channel == channel)

        # property_code:
        #   - 특정 property_code 가 주어지면: 해당 코드 or NULL (글로벌) 둘 다 후보
        #   - 없으면: 필터하지 않음 (글로벌 템플릿들 포함)
        if property_code is not None:
            q = q.filter(
                or_(
                    AutoReplyTemplate.property_code == property_code,
                    AutoReplyTemplate.property_code.is_(None),
                )
            )

        # fine_intent:
        #   - 특정 fine_intent 가 주어지면: 동일 fine_intent or NULL (generic) 둘 다 후보
        #   - 없으면: 필터하지 않음
        if fine_intent_value is not None:
            q = q.filter(
                or_(
                    AutoReplyTemplate.fine_intent == fine_intent_value,
                    AutoReplyTemplate.fine_intent.is_(None),
                )
            )

        # intent_confidence: min/max 범위 안에 드는 템플릿만 사용
        if intent_confidence is not None:
            q = q.filter(
                and_(
                    or_(
                        AutoReplyTemplate.min_intent_confidence.is_(None),
                        AutoReplyTemplate.min_intent_confidence <= intent_confidence,
                    ),
                    or_(
                        AutoReplyTemplate.max_intent_confidence.is_(None),
                        AutoReplyTemplate.max_intent_confidence >= intent_confidence,
                    ),
                )
            )

        # 정렬 우선순위:
        #   1) property_code 일치 (True > NULL)  [property_code 가 주어진 경우]
        #   2) fine_intent 일치 (True > NULL)    [fine_intent 가 주어진 경우]
        #   3) priority (작을수록 우선)
        #   4) id (작을수록 우선)
        order_by_clauses = []

        if property_code is not None:
            order_by_clauses.append(
                (AutoReplyTemplate.property_code == property_code).desc()
            )

        if fine_intent_value is not None:
            order_by_clauses.append(
                (AutoReplyTemplate.fine_intent == fine_intent_value).desc()
            )

        order_by_clauses.extend(
            [
                AutoReplyTemplate.priority.asc(),
                AutoReplyTemplate.id.asc(),
            ]
        )

        q = q.order_by(*order_by_clauses)

        return q.first()

    def list_by_filters(
        self,
        *,
        intent: IntentLike,
        locale: Optional[str] = None,
        channel: Optional[str] = None,
        property_code: Optional[str] = None,
        fine_intent: Optional[FineIntentLike] = None,
        is_active: bool = True,
    ) -> List[AutoReplyTemplate]:
        """
        Intent 기반 추천 엔진에서 사용하는 복수 템플릿 조회용 메서드.

        - sync Session 기반, 절대 await 하지 말 것.
        - priority 오름차순으로 정렬해서 반환.
        """
        intent_value = _normalize_intent(intent)
        fine_intent_value = _normalize_fine_intent(fine_intent)

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

        if fine_intent_value is not None:
            q = q.filter(AutoReplyTemplate.fine_intent == fine_intent_value)

        q = q.order_by(AutoReplyTemplate.priority.asc(), AutoReplyTemplate.id.asc())

        return q.all()
