from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.adapters.gmail_send_adapter import GmailSendAdapter
from app.db.session import get_db
from app.domain.models.conversation import (
    BulkSendJob,
    BulkSendJobStatus,
    Conversation,
    ConversationChannel,
    ConversationStatus,
    SafetyStatus,
    SendAction,
)
from app.domain.models.incoming_message import IncomingMessage, MessageDirection
from app.domain.intents import MessageActor
from app.services.conversation_thread_service import ConfirmTokenService, DraftService, SendLogService
from app.services.gmail_fetch_service import get_gmail_service
from app.api.v1.schemas.bulk_send import (
    BulkSendEligibleResponse,
    BulkSendJobDTO,
    BulkSendPreviewItemDTO,
    BulkSendPreviewRequest,
    BulkSendPreviewResponse,
    BulkSendResultItemDTO,
    BulkSendSendRequest,
    BulkSendSendResponse,
)
from app.api.v1.schemas.conversation import ConversationListItemDTO

router = APIRouter(prefix="/bulk-send", tags=["bulk-send"])


def _encode_cursor(dt: datetime, cid: UUID) -> str:
    payload = {"dt": dt.isoformat(), "id": str(cid)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
    obj = json.loads(raw)
    return datetime.fromisoformat(obj["dt"]), UUID(obj["id"])


def _safety_literal(s: SafetyStatus) -> str:
    return "pass" if s == SafetyStatus.pass_ else s.value


@router.get("/eligible-conversations", response_model=BulkSendEligibleResponse)
def eligible(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    # status=ready_to_send AND safety=pass AND draft exists(pass)
    q = (
        select(Conversation)
        .where(
            Conversation.channel == ConversationChannel.gmail,
            Conversation.status == ConversationStatus.ready_to_send,
            Conversation.safety_status == SafetyStatus.pass_,
        )
        .order_by(desc(Conversation.updated_at), desc(Conversation.id))
    )

    if cursor:
        c_dt, c_id = _decode_cursor(cursor)
        q = q.where((Conversation.updated_at < c_dt) | ((Conversation.updated_at == c_dt) & (Conversation.id < c_id)))

    rows = db.execute(q.limit(limit + 1)).scalars().all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.updated_at, last.id)
        rows = rows[:limit]

    eligible_rows: list[Conversation] = []
    for c in rows:
        d = DraftService(db).get_latest(conversation_id=c.id)
        if d and d.safety_status == SafetyStatus.pass_:
            eligible_rows.append(c)

    items = [
        ConversationListItemDTO(
            id=r.id,
            channel="gmail",
            thread_id=r.thread_id,
            status=r.status.value,
            safety_status="pass",
            last_message_id=r.last_message_id,
            updated_at=r.updated_at,
        )
        for r in eligible_rows
    ]
    return BulkSendEligibleResponse(items=items, next_cursor=next_cursor)


@router.post("/preview", response_model=BulkSendPreviewResponse)
def preview(body: BulkSendPreviewRequest, db: Session = Depends(get_db)):
    if not body.conversation_ids:
        raise HTTPException(status_code=400, detail="conversation_ids required")

    convs = db.execute(select(Conversation).where(Conversation.id.in_(body.conversation_ids))).scalars().all()
    if len(convs) != len(set(body.conversation_ids)):
        raise HTTPException(status_code=400, detail="Some conversations not found")

    job = BulkSendJob(conversation_ids=list(body.conversation_ids), status=BulkSendJobStatus.pending)
    db.add(job)
    db.flush()

    previews: list[BulkSendPreviewItemDTO] = []
    for conv in convs:
        draft = DraftService(db).get_latest(conversation_id=conv.id)

        if not draft:
            previews.append(
                BulkSendPreviewItemDTO(
                    conversation_id=conv.id,
                    thread_id=conv.thread_id,
                    draft_reply_id=None,
                    safety_status=_safety_literal(conv.safety_status),
                    can_send=False,
                    preview_content=None,
                    blocked_reason="draft_missing",
                )
            )
            continue

        can_send = (
            conv.status == ConversationStatus.ready_to_send
            and conv.safety_status == SafetyStatus.pass_
            and draft.safety_status == SafetyStatus.pass_
            and bool(conv.thread_id)
        )
        previews.append(
            BulkSendPreviewItemDTO(
                conversation_id=conv.id,
                thread_id=conv.thread_id,
                draft_reply_id=draft.id,
                safety_status=_safety_literal(draft.safety_status),
                can_send=can_send,
                preview_content=draft.content if can_send else None,
                blocked_reason=None if can_send else "not_eligible",
            )
        )

        # preview 로그 (Conversation별)
        SendLogService(db).log(conversation=conv, action=SendAction.preview, message_id=None)

    token = ConfirmTokenService().issue(
        payload={
            "t": "bulk_send",
            "job_id": str(job.id),
            "conversation_ids": [str(x) for x in job.conversation_ids],
        }
    )

    db.commit()

    return BulkSendPreviewResponse(
        job=BulkSendJobDTO(
            id=job.id,
            status=job.status.value,
            conversation_ids=job.conversation_ids,
            created_at=job.created_at,
            completed_at=job.completed_at,
        ),
        previews=previews,
        confirm_token=token,
    )


@router.post("/{job_id}/send", response_model=BulkSendSendResponse)
def send(job_id: UUID, body: BulkSendSendRequest, db: Session = Depends(get_db)):
    job = db.execute(select(BulkSendJob).where(BulkSendJob.id == job_id)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BulkSendJobStatus.pending:
        raise HTTPException(status_code=400, detail="Job not pending")

    try:
        payload = ConfirmTokenService().verify(token=body.confirm_token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid confirm token")

    if payload.get("t") != "bulk_send" or payload.get("job_id") != str(job.id):
        raise HTTPException(status_code=400, detail="Confirm token mismatch")

    gmail_service = get_gmail_service(db)
    sender = GmailSendAdapter(service=gmail_service)

    results: list[BulkSendResultItemDTO] = []
    any_failed = False
    any_sent = False

    for cid in job.conversation_ids:
        conv = db.execute(select(Conversation).where(Conversation.id == cid)).scalar_one_or_none()
        if not conv:
            any_failed = True
            results.append(
                BulkSendResultItemDTO(
                    conversation_id=cid,
                    result="failed",
                    error_code="conversation_not_found",
                    error_message="Conversation not found",
                )
            )
            continue

        draft = DraftService(db).get_latest(conversation_id=conv.id)
        if (
            not conv.thread_id
            or conv.status != ConversationStatus.ready_to_send
            or conv.safety_status != SafetyStatus.pass_
            or not draft
            or draft.safety_status != SafetyStatus.pass_
        ):
            results.append(BulkSendResultItemDTO(conversation_id=conv.id, result="skipped"))
            continue

        last_incoming = db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.thread_id == conv.thread_id, IncomingMessage.direction == MessageDirection.incoming)
            .order_by(desc(IncomingMessage.received_at), desc(IncomingMessage.id))
            .limit(1)
        ).scalar_one_or_none()

        if not last_incoming or not last_incoming.from_email:
            any_failed = True
            conv.status = ConversationStatus.blocked
            db.add(conv)
            results.append(
                BulkSendResultItemDTO(
                    conversation_id=conv.id,
                    result="failed",
                    error_code="recipient_missing",
                    error_message="Recipient email missing",
                )
            )
            continue

        try:
            resp = sender.send_reply(
                thread_id=conv.thread_id,
                to_email=last_incoming.from_email,
                subject=last_incoming.subject or "TONO Reply",
                reply_text=draft.content,
                original_message_id=None,
            )
            out_gmail_message_id = resp.get("id")
            out_thread_id = resp.get("threadId") or conv.thread_id

            if not out_thread_id:
                raise RuntimeError("Outgoing thread_id missing")

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

            SendLogService(db).log(conversation=conv, action=SendAction.bulk_send, message_id=out_msg.id)

            any_sent = True
            results.append(
                BulkSendResultItemDTO(conversation_id=conv.id, result="sent", sent_at=datetime.utcnow())
            )
        except Exception as e:
            any_failed = True
            conv.status = ConversationStatus.blocked
            db.add(conv)
            results.append(
                BulkSendResultItemDTO(
                    conversation_id=conv.id,
                    result="failed",
                    error_code="send_failed",
                    error_message=str(e),
                )
            )

    if any_failed and any_sent:
        job.status = BulkSendJobStatus.partial_failed
    elif any_failed and not any_sent:
        job.status = BulkSendJobStatus.failed
    else:
        job.status = BulkSendJobStatus.completed

    job.completed_at = datetime.utcnow()
    db.add(job)

    db.commit()

    return BulkSendSendResponse(job_id=job.id, status=job.status.value, results=results)
