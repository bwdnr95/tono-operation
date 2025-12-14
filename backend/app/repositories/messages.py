# backend/app/repositories/messages.py
from __future__ import annotations

from datetime import date
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.incoming_message import IncomingMessage
from app.domain.intents import (
    MessageActor,
    MessageActionability,
    MessageIntent,
)


class IncomingMessageRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, message_id: int):
        """
        get_by_id를 감싸는 래퍼.
        서비스 코드에서 self._msg_repo.get(message_id) 스타일로 사용.
        """
        return self.get_by_id(message_id)

    # ------------------------------------------------------------------
    # 단건 조회
    # ------------------------------------------------------------------
    def get_by_id(self, message_id: int) -> IncomingMessage | None:
        """
        PK(id) 기준으로 IncomingMessage 한 건 조회.
        AutoReplyService, 메시지 상세 조회 등에서 사용.
        """
        stmt = select(IncomingMessage).where(IncomingMessage.id == message_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        return result

    # ✅ (추가) gmail_message_id 기준 조회
    def get_by_gmail_message_id(
        self,
        gmail_message_id: str,
    ) -> IncomingMessage | None:
        """
        gmail_message_id 기준으로 IncomingMessage 한 건 조회.
        인제스트 시 중복 방지(Idempotent) 용도로 사용.
        """
        stmt = select(IncomingMessage).where(
            IncomingMessage.gmail_message_id == gmail_message_id
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        return result


    # ------------------------------------------------------------------
    # 리스트 조회: 게스트 + NEEDS_REPLY 전용
    # ------------------------------------------------------------------
    def list_recent_guest_messages(
        self,
        *,
        property_code: str | None = None,
        ota: str | None = None,
        limit: int = 50,
    ) -> Sequence[IncomingMessage]:
        """
        게스트 발신 + 답장이 필요한 메시지만 최신순으로 조회.

        - sender_actor = GUEST
        - actionability = NEEDS_REPLY
        """
        stmt = (
            select(IncomingMessage)
            .where(IncomingMessage.sender_actor == MessageActor.GUEST)
            .where(IncomingMessage.actionability == MessageActionability.NEEDS_REPLY)
            .order_by(IncomingMessage.received_at.desc())
        )

        if property_code:
            stmt = stmt.where(IncomingMessage.property_code == property_code)
        if ota:
            stmt = stmt.where(IncomingMessage.ota == ota)

        if limit:
            stmt = stmt.limit(limit)

        return self.session.execute(stmt).scalars().all()

    # ------------------------------------------------------------------
    # 인제스트용 생성 메서드
    # ------------------------------------------------------------------
    def create_from_parsed(
        self,
        *,
        gmail_message_id: str,
        thread_id: str,
        subject: str | None,
        from_email: str | None,
        received_at,
        origin,              # OriginClassificationResult
        intent_result,       # IntentClassificationResult | None
        pure_guest_message: str | None,
        ota: str | None = None,
        ota_listing_id: str | None = None,
        ota_listing_name: str | None = None,
        property_code: str | None = None,
        guest_name: str | None = None,          # 🔹 추가
        checkin_date: date | None = None,       # 🔹 추가
        checkout_date: date | None = None,      # 🔹 추가
    ) -> IncomingMessage:
        """
        파싱된 Gmail 메시지로부터 IncomingMessage 엔티티 생성.
        text_body / html_body 는 DB에 저장하지 않는다 (pure_guest_message만 저장).
        """
        msg = IncomingMessage(
            gmail_message_id=gmail_message_id,
            thread_id=thread_id,
            subject=subject,
            from_email=from_email,
            received_at=received_at,

            sender_actor=origin.actor,
            actionability=origin.actionability,

            intent=intent_result.intent if intent_result else None,
            intent_confidence=(
                intent_result.confidence if intent_result else None
            ),

            pure_guest_message=pure_guest_message,

            ota=ota,
            ota_listing_id=ota_listing_id,
            ota_listing_name=ota_listing_name,
            property_code=property_code,

            guest_name=guest_name,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
        )

        self.session.add(msg)
        self.session.flush()
        return msg
