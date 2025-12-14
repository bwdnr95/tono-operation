from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.adapters.gmail_send_adapter import GmailSendAdapter
from app.db.session import get_db
from app.domain.intents import MessageActor
from app.domain.models.conversation import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    SafetyStatus,
    SendAction,
)
from app.domain.models.incoming_message import IncomingMessage, MessageDirection
from app.services.auto_reply_service import AutoReplyService  # ✅ 추가: 기존 LLM 파이프라인 재사용
from app.services.conversation_thread_service import (
    ConfirmTokenService,
    DraftService,
    SafetyGuardService,
    SendLogService,
    apply_safety_to_conversation,
)
from app.services.gmail_fetch_service import get_gmail_service
from app.api.v1.schemas.conversation import (
    ConversationDTO,
    ConversationDetailResponse,
    ConversationListItemDTO,
    ConversationListResponse,
    ConversationMessageDTO,
    DraftGenerateRequest,
    DraftGenerateResponse,
    DraftPatchRequest,
    DraftReplyDTO,
    SendPreviewResponse,
    SendRequest,
    SendResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _encode_cursor(dt: datetime, cid: UUID) -> str:
    payload = {"dt": dt.isoformat(), "id": str(cid)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
    obj = json.loads(raw)
    return datetime.fromisoformat(obj["dt"]), UUID(obj["id"])


def _safety_literal(s: SafetyStatus) -> str:
    return "pass" if s == SafetyStatus.pass_ else s.value


def _enum_or_raw_to_str(v) -> Optional[str]:
    """
    DB/ORM에서 enum/string/int 등 어떤 형태로 오든,
    API contract(intent: string|null) 맞게 string|null로 강제 변환.
    """
    if v is None:
        return None
    if hasattr(v, "value"):
        try:
            return str(v.value)
        except Exception:
            return str(v)
    return str(v)


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    status_: Optional[str] = Query(None, alias="status"),
    safety_status: Optional[str] = Query(None),
    thread_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = select(Conversation).where(Conversation.channel == ConversationChannel.gmail)

    if thread_id:
        q = q.where(Conversation.thread_id == thread_id)

    if status_:
        try:
            q = q.where(Conversation.status == ConversationStatus(status_))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid status")

    if safety_status:
        try:
            q = q.where(Conversation.safety_status == SafetyStatus(safety_status))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid safety_status")

    q = q.order_by(desc(Conversation.updated_at), desc(Conversation.id))

    if cursor:
        c_dt, c_id = _decode_cursor(cursor)
        q = q.where((Conversation.updated_at < c_dt) | ((Conversation.updated_at == c_dt) & (Conversation.id < c_id)))

    rows = db.execute(q.limit(limit + 1)).scalars().all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.updated_at, last.id)
        rows = rows[:limit]

    items = [
        ConversationListItemDTO(
            id=r.id,
            channel="gmail",
            thread_id=r.thread_id,
            status=r.status.value,
            safety_status=_safety_literal(r.safety_status),
            last_message_id=r.last_message_id,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return ConversationListResponse(items=items, next_cursor=next_cursor)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation_detail(conversation_id: UUID, db: Session = Depends(get_db)):
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = db.execute(
        select(IncomingMessage)
        .where(IncomingMessage.thread_id == conv.thread_id)
        .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
    ).scalars().all()

    msg_dtos: list[ConversationMessageDTO] = []
    for m in msgs:
        sender_actor = _enum_or_raw_to_str(getattr(m, "sender_actor", None)) or "UNKNOWN"
        if sender_actor not in ("GUEST", "HOST", "SYSTEM", "UNKNOWN"):
            sender_actor = "UNKNOWN"

        msg_dtos.append(
            ConversationMessageDTO(
                id=m.id,
                thread_id=m.thread_id,
                direction=_enum_or_raw_to_str(getattr(m, "direction", None)) or "incoming",
                sender_actor=sender_actor,
                subject=m.subject,
                from_email=m.from_email,
                received_at=m.received_at,
                pure_guest_message=m.pure_guest_message,
                content=getattr(m, "content", None),
                intent=_enum_or_raw_to_str(getattr(m, "intent", None)),
                intent_confidence=getattr(m, "intent_confidence", None),
            )
        )

    draft = DraftService(db).get_latest(conversation_id=conv.id)
    draft_dto = None
    if draft:
        draft_dto = DraftReplyDTO(
            id=draft.id,
            conversation_id=draft.conversation_id,
            thread_id=draft.thread_id,
            content=draft.content,
            safety_status=_safety_literal(draft.safety_status),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )

    return ConversationDetailResponse(
        conversation=ConversationDTO(
            id=conv.id,
            channel="gmail",
            thread_id=conv.thread_id,
            status=conv.status.value,
            safety_status=_safety_literal(conv.safety_status),
            last_message_id=conv.last_message_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        ),
        messages=msg_dtos,
        draft_reply=draft_dto,
    )


@router.post("/{conversation_id}/draft-reply:generate", response_model=DraftGenerateResponse)
async def generate_draft(conversation_id: UUID, body: DraftGenerateRequest, db: Session = Depends(get_db)):
    """
    ✅ 기존 코드 참고: 기존엔 DraftService.generate_draft(thread_id=...)를 호출했음. :contentReference[oaicite:0]{index=0}
    ✅ 변경: 기존 AutoReplyService(LLM 파이프라인)를 Conversation(thread) 단위로 호출하여 draft content 생성
    """
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not conv.thread_id:
        raise HTTPException(status_code=400, detail="thread_id required")

    # ✅ 실제 LLM 호출: 기존 auto_reply 로직 재사용 (thread 전체 맥락 반영)
    auto_reply = AutoReplyService(db)
    suggestion = await auto_reply.suggest_reply_for_conversation(
        thread_id=conv.thread_id,
        ota=getattr(conv, "ota", None),
        locale="ko",
        property_code=getattr(conv, "property_code", None),
        use_llm=True,
    )

    if not suggestion or not getattr(suggestion, "reply_text", None):
        raise HTTPException(status_code=400, detail="Failed to generate draft reply")

    content = suggestion.reply_text

    safety, _reasons = SafetyGuardService(db).evaluate_text(text=content)
    apply_safety_to_conversation(conv, safety)

    # ✅ draft 저장은 기존 DraftService(upsert_latest) 그대로 유지
    draft = DraftService(db).upsert_latest(conversation=conv, content=content, safety=safety)

    db.commit()

    return DraftGenerateResponse(
        draft_reply=DraftReplyDTO(
            id=draft.id,
            conversation_id=draft.conversation_id,
            thread_id=draft.thread_id,
            content=draft.content,
            safety_status=_safety_literal(draft.safety_status),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
    )


@router.patch("/{conversation_id}/draft-reply", response_model=DraftGenerateResponse)
def edit_draft(conversation_id: UUID, body: DraftPatchRequest, db: Session = Depends(get_db)):
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not conv.thread_id:
        raise HTTPException(status_code=400, detail="thread_id required")

    safety, _reasons = SafetyGuardService(db).evaluate_text(text=body.content)
    apply_safety_to_conversation(conv, safety)

    draft = DraftService(db).upsert_latest(conversation=conv, content=body.content, safety=safety)
    db.commit()

    return DraftGenerateResponse(
        draft_reply=DraftReplyDTO(
            id=draft.id,
            conversation_id=draft.conversation_id,
            thread_id=draft.thread_id,
            content=draft.content,
            safety_status=_safety_literal(draft.safety_status),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
    )


@router.post("/{conversation_id}/send:preview", response_model=SendPreviewResponse)
def preview_send(conversation_id: UUID, db: Session = Depends(get_db)):
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    draft = DraftService(db).get_latest(conversation_id=conv.id)
    if not draft:
        raise HTTPException(status_code=400, detail="Draft reply not found")

    safety_literal = _safety_literal(draft.safety_status)
    can_send = safety_literal == "pass" and conv.status == ConversationStatus.ready_to_send

    token = ConfirmTokenService().issue(
        payload={
            "t": "conversation_send",
            "conversation_id": str(conv.id),
            "draft_reply_id": str(draft.id),
            "thread_id": conv.thread_id,
        }
    )

    SendLogService(db).log(conversation=conv, action=SendAction.preview, message_id=None)
    db.commit()

    return SendPreviewResponse(
        conversation_id=conv.id,
        draft_reply_id=draft.id,
        safety_status=safety_literal,
        can_send=can_send,
        preview_content=draft.content,
        confirm_token=token,
    )


@router.post("/{conversation_id}/send", response_model=SendResponse)
def send_reply(conversation_id: UUID, body: SendRequest, db: Session = Depends(get_db)):
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status != ConversationStatus.ready_to_send:
        raise HTTPException(status_code=400, detail="Conversation is not ready_to_send")

    draft = DraftService(db).get_latest(conversation_id=conv.id)
    if not draft or str(draft.id) != str(body.draft_reply_id):
        raise HTTPException(status_code=400, detail="Draft reply not found")
    if draft.safety_status != SafetyStatus.pass_ or conv.safety_status != SafetyStatus.pass_:
        raise HTTPException(status_code=400, detail="Safety status is not pass")

    try:
        payload = ConfirmTokenService().verify(token=body.confirm_token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid confirm token")

    if payload.get("t") != "conversation_send":
        raise HTTPException(status_code=400, detail="Invalid confirm token type")
    if payload.get("conversation_id") != str(conv.id) or payload.get("draft_reply_id") != str(draft.id):
        raise HTTPException(status_code=400, detail="Confirm token mismatch")
    if payload.get("thread_id") != conv.thread_id:
        raise HTTPException(status_code=400, detail="Confirm token thread mismatch")

    last_incoming = db.execute(
        select(IncomingMessage)
        .where(IncomingMessage.thread_id == conv.thread_id, IncomingMessage.direction == MessageDirection.incoming)
        .order_by(desc(IncomingMessage.received_at), desc(IncomingMessage.id))
        .limit(1)
    ).scalar_one_or_none()
    if not last_incoming or not last_incoming.from_email:
        conv.status = ConversationStatus.blocked
        db.add(conv)
        db.commit()
        raise HTTPException(status_code=400, detail="Recipient email not found")

    gmail_service = get_gmail_service(db)
    sender = GmailSendAdapter(service=gmail_service)
    try:
        resp = sender.send_reply(
            thread_id=conv.thread_id,
            to_email=last_incoming.from_email,
            subject=last_incoming.subject or "TONO Reply",
            reply_text=draft.content,
            original_message_id=None,
        )
    except Exception as e:
        conv.status = ConversationStatus.blocked
        db.add(conv)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Send failed: {e}")

    out_gmail_message_id = resp.get("id")
    out_thread_id = resp.get("threadId") or conv.thread_id
    if not out_thread_id:
        conv.status = ConversationStatus.blocked
        db.add(conv)
        db.commit()
        raise HTTPException(status_code=500, detail="Outgoing thread_id missing. Send blocked.")

    out_msg = IncomingMessage(
        gmail_message_id=str(out_gmail_message_id),
        thread_id=out_thread_id,
        subject=last_incoming.subject,
        from_email=None,
        received_at=datetime.utcnow(),
        pure_guest_message=None,
        sender_actor=MessageActor.HOST,
        actionability=last_incoming.actionability,
        has_attachment=False,
        is_system_generated=True,
        direction=MessageDirection.outgoing,
        content=draft.content,
        intent=None,
        intent_confidence=None,
        ota=last_incoming.ota,
        ota_listing_id=last_incoming.ota_listing_id,
        ota_listing_name=last_incoming.ota_listing_name,
        property_code=last_incoming.property_code,
        guest_name=last_incoming.guest_name,
        checkin_date=last_incoming.checkin_date,
        checkout_date=last_incoming.checkout_date,
    )
    db.add(out_msg)
    db.flush()

    conv.thread_id = out_thread_id
    conv.last_message_id = out_msg.id
    conv.status = ConversationStatus.sent
    conv.updated_at = datetime.utcnow()
    db.add(conv)

    SendLogService(db).log(conversation=conv, action=SendAction.send, message_id=out_msg.id)

    db.commit()

    return SendResponse(conversation_id=conv.id, sent_at=datetime.utcnow(), status="sent")
