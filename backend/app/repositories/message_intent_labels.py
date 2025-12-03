from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.domain.models.message_intent_label import MessageIntentLabel
from app.domain.intents import MessageIntent
from app.domain.intents.types import IntentLabelSource


class MessageIntentLabelRepository:
    """
    message_intent_labels 테이블에 대한 sync 레포지토리.

    - Intent 라벨 생성
    - 특정 메시지에 대한 라벨 목록 조회
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------
    def create_label(
        self,
        *,
        message_id: int,
        intent: MessageIntent,
        source: IntentLabelSource,
    ) -> MessageIntentLabel:
        label = MessageIntentLabel(
            message_id=message_id,
            intent=intent,
            source=source,
        )
        self.session.add(label)
        self.session.flush()
        return label

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------
    def list_labels_for_message(
        self,
        message_id: int,
    ) -> List[MessageIntentLabel]:
        """
        특정 메시지에 달린 Intent 라벨들을 생성일 순으로 리턴.
        """
        q = (
            self.session.query(MessageIntentLabel)
            .filter(MessageIntentLabel.message_id == message_id)
            .order_by(MessageIntentLabel.created_at.asc())
        )
        return q.all()
