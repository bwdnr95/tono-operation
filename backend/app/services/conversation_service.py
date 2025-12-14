from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import and_, asc, desc, select
from sqlalchemy.orm import Session

from app.services.auto_reply_service import AutoReplyService

from app.domain.models.conversation import (
    BulkSendJob,
    BulkSendJobStatus,
    Conversation,
    ConversationDraftReply,
    ConversationStage,
    ConversationStatus,
    DraftCreatedBy,
    SafetyGuardResult,
    SafetyStatus,
    SendActionLog,
    SendActionType,
)
from app.domain.models.incoming_message import IncomingMessage

def _encode_cursor(dt: datetime, id_: uuid.UUID) -> str:
    raw = json.dumps({"dt": dt.isoformat(), "id": str(id_)}, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
    obj = json.loads(raw)
    return datetime.fromisoformat(obj["dt"]), uuid.UUID(obj["id"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def apply_safety_to_conversation(conversation: Conversation, safety_status: SafetyStatus) -> None:
    conversation.safety_status = safety_status
    conversation.stage = ConversationStage.drafted

    if safety_status == SafetyStatus.pass_:
        conversation.status = ConversationStatus.ready_to_send
    elif safety_status == SafetyStatus.review:
        conversation.status = ConversationStatus.needs_review
    else:
        conversation.status = ConversationStatus.blocked


class ConversationDraftService:
    db: Session

    def _build_prompt(self, *, messages: Sequence[IncomingMessage], summary_text: str | None) -> str:
        parts: list[str] = []
        if summary_text:
            parts.append(f"[Conversation Summary]\n{summary_text}\n")
        parts.append("[Messages]")
        for m in messages[-12:]:
            who = m.sender_actor.value if hasattr(m.sender_actor, "value") else str(m.sender_actor)
            body = m.pure_guest_message or ""
            parts.append(f"- {who}: {body}".strip())
        parts.append("\n[Instruction]\nWrite a helpful host reply in Korean. Be concise and polite.")
        return "\n".join(parts).strip()

    def generate_llm_draft(self, *, conversation: Conversation) -> str:
        """
        Conversation 기반 draft 생성.
        - 기존 AutoReplyService(단일 메시지 LLM 파이프라인)를 재사용하여,
          Conversation(thread) 전체 맥락을 LLM 입력에 반영한다.
        """
        if not conversation.thread_id:
            raise ValueError("conversation.thread_id is required")

        auto_reply = AutoReplyService(self.db)

        import asyncio

        async def _run() -> str:
            suggestion = await auto_reply.suggest_reply_for_conversation(
                thread_id=conversation.thread_id,
                locale="ko",
                ota=getattr(conversation, "ota", None),
                property_code=getattr(conversation, "property_code", None),
                use_llm=True,
            )
            if not suggestion:
                return "안녕하세요! 문의 주셔서 감사합니다. 내용을 확인하고 안내드리겠습니다."
            return suggestion.reply_text

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_run())
        else:
            raise RuntimeError(
                "generate_llm_draft must be called from sync context; "
                "use AutoReplyService.suggest_reply_for_conversation in async context"
            )

    def upsert_draft(
        self,
        *,
        conversation: Conversation,
        content: str,
        created_by: DraftCreatedBy,
        safety_status: SafetyStatus,
    ) -> ConversationDraftReply:
        draft = self.db.execute(
            select(ConversationDraftReply)
            .where(ConversationDraftReply.conversation_id == conversation.id)
            .order_by(desc(ConversationDraftReply.created_at))
            .limit(1)
        ).scalar_one_or_none()

        if draft is None:
            draft = ConversationDraftReply(
                conversation_id=conversation.id,
                content=content,
                created_by=created_by,
                safety_status=safety_status,
            )
            self.db.add(draft)
        else:
            draft.content = content
            draft.created_by = created_by
            draft.safety_status = safety_status

        conversation.stage = ConversationStage.drafted
        conversation.updated_at = _now_utc()
        self.db.flush()
        return draft


class SendActionLogService:
    db: Session

    def log(
        self,
        *,
        property_code: str,
        actor: str,
        action: SendActionType,
        conversation_id: uuid.UUID | None,
        bulk_send_job_id: uuid.UUID | None,
        message_id: int | None,
        payload_json: dict,
    ) -> SendActionLog:
        row = SendActionLog(
            id=uuid.uuid4(),
            property_code=property_code,
            actor=actor,
            action=action,
            conversation_id=conversation_id,
            bulk_send_job_id=bulk_send_job_id,
            message_id=message_id,
            payload_json=payload_json,
            created_at=_now_utc(),
        )
        self.db.add(row)
        self.db.flush()
        return row
