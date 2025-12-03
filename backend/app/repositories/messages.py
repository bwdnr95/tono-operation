from __future__ import annotations

from typing import Optional, Any

from sqlalchemy.orm import Session

from app.domain.models.incoming_message import IncomingMessage
from app.domain.intents import (
    MessageActor,
    MessageActionability,
    MessageIntent,
)


class IncomingMessageRepository:
    """
    IncomingMessage 테이블에 대한 영속 계층.

    - Gmail에서 파싱된 메시지 + Origin/Intent 결과를 저장
    - 메시지 리스트/상세 조회
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------
    def create_from_parsed(
        self,
        *,
        gmail_message_id: str,
        thread_id: Optional[str],
        subject: Optional[str],
        from_email: Optional[str],
        text_body: Optional[str],
        html_body: Optional[str],
        received_at,
        origin: Any,
        intent_result: Any | None,
        pure_guest_message: Optional[str],
    ) -> IncomingMessage:
        """
        ParsedInternalMessage + Origin/Intent 분류 결과를 기반으로
        IncomingMessage 레코드를 생성.

        이미 동일한 gmail_message_id가 있으면 새로 만들지 않고 기존 레코드를 반환.
        """

        # 🔹 1) 중복 방지: gmail_message_id 기준으로 조회
        existing = (
            self.session.query(IncomingMessage)
            .filter_by(gmail_message_id=gmail_message_id)
            .first()
        )
        if existing:
            return existing

        # 🔹 2) Origin 매핑
        if origin and hasattr(origin, "actor"):
            if isinstance(origin.actor, MessageActor):
                sender_actor = origin.actor
            else:
                try:
                    sender_actor = MessageActor(
                        getattr(origin.actor, "value", origin.actor)
                    )
                except Exception:
                    sender_actor = MessageActor.UNKNOWN
        else:
            sender_actor = MessageActor.UNKNOWN

        if origin and hasattr(origin, "actionability"):
            if isinstance(origin.actionability, MessageActionability):
                actionability = origin.actionability
            else:
                try:
                    actionability = MessageActionability(
                        getattr(origin.actionability, "value", origin.actionability)
                    )
                except Exception:
                    actionability = MessageActionability.UNKNOWN
        else:
            actionability = MessageActionability.UNKNOWN

        # 🔹 3) Intent 매핑
        primary_intent: MessageIntent | None = None
        intent_confidence: float | None = None

        if intent_result is not None:
            raw_int = getattr(intent_result, "intent", None)

            if isinstance(raw_int, MessageIntent):
                primary_intent = raw_int
            elif isinstance(raw_int, str):
                try:
                    primary_intent = MessageIntent[raw_int]
                except KeyError:
                    primary_intent = None
            elif hasattr(raw_int, "name"):
                try:
                    primary_intent = MessageIntent[raw_int.name]
                except KeyError:
                    primary_intent = None
            elif hasattr(raw_int, "value"):
                try:
                    primary_intent = MessageIntent(raw_int.value)
                except Exception:
                    primary_intent = None

            intent_confidence = getattr(intent_result, "confidence", None)

        # 🔹 4) 실제 INSERT
        msg = IncomingMessage(
            gmail_message_id=gmail_message_id,
            thread_id=thread_id,
            subject=subject,
            from_email=from_email,
            text_body=text_body,
            html_body=html_body,
            received_at=received_at,
            pure_guest_message=pure_guest_message,
            sender_actor=sender_actor,
            actionability=actionability,
            intent=primary_intent,
            intent_confidence=intent_confidence,
        )

        self.session.add(msg)
        self.session.flush()
        self.session.refresh(msg)
        return msg

    # ------------------------------------------------------------------
    # READ: 리스트
    # ------------------------------------------------------------------
    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        only_actionable: bool = True,
    ) -> list[IncomingMessage]:
        """
        최근 메시지 목록 조회.

        - 기본: 게스트 + 답변 필요 메시지만
        - received_at DESC
        """
        q = self.session.query(IncomingMessage)

        if only_actionable:
            q = q.filter(
                IncomingMessage.sender_actor == MessageActor.GUEST,
                IncomingMessage.actionability == MessageActionability.NEEDS_REPLY,
            )

        q = q.order_by(IncomingMessage.received_at.desc())

        if offset:
            q = q.offset(offset)
        if limit:
            q = q.limit(limit)

        return q.all()

    # ------------------------------------------------------------------
    # READ: 상세
    # ------------------------------------------------------------------
    def get_by_id(self, message_id: int) -> IncomingMessage | None:
        """
        PK 기반 단일 메시지 조회.
        """
        return self.session.get(IncomingMessage, message_id)
