from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.domain.intents import MessageIntent
from app.domain.intents.types import IntentLabelSource
from app.domain.models.message_intent_label import MessageIntentLabel
from app.repositories.message_intent_labels import MessageIntentLabelRepository


class MessageIntentLabelService:
    """
    Intent 라벨 기록용 서비스 계층.

    - SYSTEM / HUMAN / ML 등 label_source 단일 책임
    - 실제 DB I/O는 Repository에 위임
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = MessageIntentLabelRepository(db)

    def add_system_label_only(
        self,
        *,
        message_id: int,
        intent: MessageIntent,
        confidence: Optional[float] = None,  # 현재는 사용 안 하지만 시그니처만 유지
    ) -> MessageIntentLabel:
        """
        SYSTEM 소스의 Intent 라벨만 기록.

        confidence는 message_intent_labels 테이블에 별도 컬럼이 없을 수 있으니
        지금 단계에서는 저장하지 않고, 향후 컬럼 추가 시 확장 가능하도록 인자만 유지.
        """
        label = self.repo.create_label(
            message_id=message_id,
            intent=intent,
            source=IntentLabelSource.SYSTEM,
        )
        # 커밋은 상위 서비스/스크립트에서 통합적으로 처리
        return label
