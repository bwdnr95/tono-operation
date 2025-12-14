from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.domain.models.conversation import (
    BulkSendJob,
    BulkSendJobStatus,
    Conversation,
    ConversationChannel,
    ConversationStatus,
    DraftReply,
    SafetyStatus,
    SendAction,
    SendActionLog,
)
from app.domain.models.incoming_message import IncomingMessage, MessageDirection
from app.domain.intents import MessageActor


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ConfirmTokenError(Exception):
    pass


class ConfirmTokenService:
    """
    Preview -> Send 강제를 위해 stateless confirm_token 사용.
    DB 저장 없이도 token 서명/만료/내용 매칭으로 검증한다.
    """
    def __init__(self) -> None:
        secret = os.getenv("TONO_CONFIRM_TOKEN_SECRET") or os.getenv("SECRET_KEY") or "tono-dev-secret"
        self._secret = secret.encode("utf-8")

    def issue(self, *, payload: dict, ttl_seconds: int = 600) -> str:
        exp = int((_now_utc() + timedelta(seconds=ttl_seconds)).timestamp())
        body = dict(payload)
        body["exp"] = exp
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        sig = hmac.new(self._secret, raw, hashlib.sha256).digest()
        token = (
            base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
            + "."
            + base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
        )
        return token

    def verify(self, *, token: str) -> dict:
        try:
            raw_b64, sig_b64 = token.split(".", 1)
            raw = base64.urlsafe_b64decode(raw_b64 + "==")
            sig = base64.urlsafe_b64decode(sig_b64 + "==")
        except Exception as e:
            raise ConfirmTokenError("invalid_format") from e

        expected = hmac.new(self._secret, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, sig):
            raise ConfirmTokenError("invalid_signature")

        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise ConfirmTokenError("invalid_payload") from e

        exp = body.get("exp")
        if not isinstance(exp, int) or int(_now_utc().timestamp()) > exp:
            raise ConfirmTokenError("expired")

        return body


def apply_safety_to_conversation(conversation: Conversation, safety: SafetyStatus) -> None:
    conversation.safety_status = safety
    if safety == SafetyStatus.pass_:
        conversation.status = ConversationStatus.ready_to_send
    elif safety == SafetyStatus.review:
        conversation.status = ConversationStatus.needs_review
    else:
        conversation.status = ConversationStatus.blocked


@dataclass
class ConversationService:
    db: Session

    def upsert_for_thread(self, *, channel: ConversationChannel, thread_id: str, last_message_id: int | None) -> Conversation:
        if not thread_id:
            raise ValueError("thread_id required")

        existing = self.db.execute(
            select(Conversation).where(Conversation.channel == channel, Conversation.thread_id == thread_id)
        ).scalar_one_or_none()

        if existing is None:
            conv = Conversation(
                channel=channel,
                thread_id=thread_id,
                status=ConversationStatus.open,
                safety_status=SafetyStatus.pass_,
                last_message_id=last_message_id,
            )
            self.db.add(conv)
            self.db.flush()
            return conv

        existing.last_message_id = last_message_id
        existing.updated_at = _now_utc()
        self.db.add(existing)
        self.db.flush()
        return existing

    def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        return self.db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()


@dataclass
class DraftService:
    db: Session

    def generate_draft(self, *, thread_id: str) -> str:
        msgs = self.db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.thread_id == thread_id)
            .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
        ).scalars().all()

        last_guest = None
        for m in reversed(msgs):
            if m.direction == MessageDirection.incoming and m.sender_actor == MessageActor.GUEST:
                if (m.pure_guest_message or "").strip():
                    last_guest = m
                    break

        if last_guest:
            guest_text = (last_guest.pure_guest_message or "").strip()
            return (
                f'안녕하세요! 문의 주셔서 감사합니다. 말씀하신 내용("{guest_text[:120]}") 확인했습니다. '
                "추가로 필요한 정보가 있으면 알려주시면 바로 도와드리겠습니다."
            )
        return "안녕하세요! 문의 주셔서 감사합니다. 내용을 확인하고 안내드리겠습니다."

    def upsert_latest(self, *, conversation: Conversation, content: str, safety: SafetyStatus) -> DraftReply:
        latest = self.db.execute(
            select(DraftReply)
            .where(DraftReply.conversation_id == conversation.id)
            .order_by(desc(DraftReply.created_at))
            .limit(1)
        ).scalar_one_or_none()

        if latest is None:
            dr = DraftReply(
                conversation_id=conversation.id,
                thread_id=conversation.thread_id,
                content=content,
                safety_status=safety,
            )
            self.db.add(dr)
            self.db.flush()
            return dr

        latest.content = content
        latest.thread_id = conversation.thread_id
        latest.safety_status = safety
        latest.updated_at = _now_utc()
        self.db.add(latest)
        self.db.flush()
        return latest

    def get_latest(self, *, conversation_id: uuid.UUID) -> DraftReply | None:
        return self.db.execute(
            select(DraftReply)
            .where(DraftReply.conversation_id == conversation_id)
            .order_by(desc(DraftReply.created_at))
            .limit(1)
        ).scalar_one_or_none()


@dataclass
class SafetyGuardService:
    db: Session

    def evaluate_text(self, *, text: str) -> tuple[SafetyStatus, list[str]]:
        lower = (text or "").lower()
        reason_codes: list[str] = []
        status = SafetyStatus.pass_

        block_keywords = ["suicide", "self-harm", "kill", "weapon", "gun", "bomb", "illegal", "drugs", "cvv", "card number"]
        review_keywords = ["phone", "kakao", "whatsapp", "wechat", "email", "address", "account number", "passport"]

        if any(k in lower for k in block_keywords):
            status = SafetyStatus.block
            reason_codes.append("sensitive_or_illegal")
        elif any(k in lower for k in review_keywords):
            status = SafetyStatus.review
            reason_codes.append("pii_or_contact_exchange")

        return status, reason_codes


@dataclass
class SendLogService:
    db: Session

    def log(self, *, conversation: Conversation, action: SendAction, message_id: int | None = None) -> SendActionLog:
        rec = SendActionLog(
            conversation_id=conversation.id,
            thread_id=conversation.thread_id,
            message_id=message_id,
            action=action,
        )
        self.db.add(rec)
        self.db.flush()
        return rec


@dataclass
class BulkSendService:
    db: Session

    def create_job(self, *, conversation_ids: list[uuid.UUID]) -> BulkSendJob:
        job = BulkSendJob(conversation_ids=conversation_ids, status=BulkSendJobStatus.pending)
        self.db.add(job)
        self.db.flush()
        return job
