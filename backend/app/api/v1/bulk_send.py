"""
Bulk Send API - 단순화된 버전
- Preview 없음
- Job 없음  
- confirm_token 없음
- 선택된 Conversation들을 직접 순차 발송
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.adapters.gmail_send_adapter import GmailSendAdapter
from app.db.session import get_db
from app.domain.models.conversation import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    SafetyStatus,
    SendAction,
)
from app.domain.models.incoming_message import IncomingMessage, MessageDirection
from app.domain.intents import MessageActor
from app.services.conversation_thread_service import DraftService, SendLogService
from app.services.gmail_fetch_service import get_gmail_service
from app.services.send_event_handler import SendEventHandler
from app.api.v1.schemas.conversation import ConversationListItemDTO

router = APIRouter(prefix="/bulk-send", tags=["bulk-send"])


# ============================================================
# Schemas
# ============================================================

class BulkSendEligibleResponse(BaseModel):
    """Bulk Send 가능한 Conversation 목록"""
    items: List[ConversationListItemDTO]
    next_cursor: Optional[str] = None


class BulkSendRequest(BaseModel):
    """Bulk Send 요청 - conversation_ids만 필요"""
    conversation_ids: List[UUID]


class BulkSendResultItem(BaseModel):
    """개별 Conversation 발송 결과"""
    conversation_id: UUID
    result: str  # "sent" | "skipped" | "failed"
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None


class BulkSendResponse(BaseModel):
    """Bulk Send 응답"""
    total: int
    sent: int
    skipped: int
    failed: int
    results: List[BulkSendResultItem]


# ============================================================
# Helpers
# ============================================================

def _encode_cursor(dt: datetime, cid: UUID) -> str:
    payload = {"dt": dt.isoformat(), "id": str(cid)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
    obj = json.loads(raw)
    return datetime.fromisoformat(obj["dt"]), UUID(obj["id"])


# ============================================================
# Endpoints
# ============================================================

@router.get("/eligible-conversations", response_model=BulkSendEligibleResponse)
def get_eligible_conversations(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Bulk Send 가능한 Conversation 목록 조회
    조건: status=ready_to_send AND safety=pass AND draft(pass) 존재
    """
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
        q = q.where(
            (Conversation.updated_at < c_dt) | 
            ((Conversation.updated_at == c_dt) & (Conversation.id < c_id))
        )

    rows = db.execute(q.limit(limit + 1)).scalars().all()
    
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.updated_at, last.id)
        rows = rows[:limit]

    # Draft가 pass인 것만 필터링
    eligible_rows: list[Conversation] = []
    for conv in rows:
        draft = DraftService(db).get_latest(conversation_id=conv.id)
        if draft and draft.safety_status == SafetyStatus.pass_:
            eligible_rows.append(conv)

    # 각 conversation의 게스트 정보 조회
    items = []
    for r in eligible_rows:
        # 해당 thread의 첫 번째 incoming 메시지에서 게스트 정보 가져오기
        guest_msg = db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == r.airbnb_thread_id)
            .where(IncomingMessage.direction == MessageDirection.incoming)
            .where(IncomingMessage.guest_name.isnot(None))
            .order_by(asc(IncomingMessage.received_at))
            .limit(1)
        ).scalar_one_or_none()
        
        items.append(ConversationListItemDTO(
            id=r.id,
            channel="gmail",
            airbnb_thread_id=r.airbnb_thread_id,
            status=r.status.value,
            safety_status="pass",
            last_message_id=r.last_message_id,
            updated_at=r.updated_at,
            guest_name=guest_msg.guest_name if guest_msg else None,
            checkin_date=str(guest_msg.checkin_date) if guest_msg and guest_msg.checkin_date else None,
            checkout_date=str(guest_msg.checkout_date) if guest_msg and guest_msg.checkout_date else None,
        ))
    
    return BulkSendEligibleResponse(items=items, next_cursor=next_cursor)


@router.post("/send", response_model=BulkSendResponse)
def bulk_send(body: BulkSendRequest, db: Session = Depends(get_db)):
    """
    Bulk Send 실행
    - Preview/Job/Token 없음
    - 선택된 conversation_ids를 순차 발송
    - 실패해도 다음 건 계속 진행
    """
    if not body.conversation_ids:
        return BulkSendResponse(total=0, sent=0, skipped=0, failed=0, results=[])

    gmail_service = get_gmail_service(db)
    sender = GmailSendAdapter(service=gmail_service)

    results: list[BulkSendResultItem] = []
    sent_count = 0
    skipped_count = 0
    failed_count = 0

    for cid in body.conversation_ids:
        conv = db.execute(
            select(Conversation).where(Conversation.id == cid)
        ).scalar_one_or_none()
        
        if not conv:
            failed_count += 1
            results.append(BulkSendResultItem(
                conversation_id=cid,
                result="failed",
                error_message="Conversation not found",
            ))
            continue

        # 발송 조건 체크
        draft = DraftService(db).get_latest(conversation_id=conv.id)
        
        skip_reason = None
        if not conv.airbnb_thread_id:
            skip_reason = "airbnb_thread_id missing"
        elif conv.status != ConversationStatus.ready_to_send:
            skip_reason = f"status is {conv.status.value}"
        elif conv.safety_status != SafetyStatus.pass_:
            skip_reason = f"safety is {conv.safety_status.value}"
        elif not draft:
            skip_reason = "draft not found"
        elif draft.safety_status != SafetyStatus.pass_:
            skip_reason = f"draft safety is {draft.safety_status.value}"
        elif draft.airbnb_thread_id != conv.airbnb_thread_id:
            skip_reason = "draft airbnb_thread_id mismatch"

        if skip_reason:
            skipped_count += 1
            results.append(BulkSendResultItem(
                conversation_id=conv.id,
                result="skipped",
                error_message=skip_reason,
            ))
            continue

        # 수신자 이메일 조회
        last_incoming = db.execute(
            select(IncomingMessage)
            .where(
                IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id,
                IncomingMessage.direction == MessageDirection.incoming
            )
            .order_by(desc(IncomingMessage.received_at), desc(IncomingMessage.id))
            .limit(1)
        ).scalar_one_or_none()

        if not last_incoming:
            failed_count += 1
            conv.status = ConversationStatus.blocked
            db.add(conv)
            results.append(BulkSendResultItem(
                conversation_id=conv.id,
                result="failed",
                error_message="No incoming message found",
            ))
            continue

        # reply_to가 없으면 발송 불가
        if not last_incoming.reply_to:
            failed_count += 1
            conv.status = ConversationStatus.blocked
            db.add(conv)
            results.append(BulkSendResultItem(
                conversation_id=conv.id,
                result="failed",
                error_message="Reply-To not found. Cannot send reply.",
            ))
            continue

        # Gmail 발송
        try:
            resp = sender.send_reply(
                airbnb_thread_id=conv.airbnb_thread_id,
                to_email=last_incoming.reply_to,
                subject=last_incoming.subject or "TONO Reply",
                reply_text=draft.content,
                original_message_id=None,
            )
            
            out_gmail_message_id = resp.get("id")
            out_thread_id = resp.get("threadId") or conv.airbnb_thread_id

            if not out_thread_id:
                raise RuntimeError("Outgoing airbnb_thread_id missing")

            # Outgoing 메시지 저장
            out_msg = IncomingMessage(
                gmail_message_id=str(out_gmail_message_id),
                airbnb_thread_id=out_thread_id,
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

            # Conversation 상태 업데이트
            conv.airbnb_thread_id = out_thread_id
            conv.last_message_id = out_msg.id
            conv.status = ConversationStatus.sent
            conv.updated_at = datetime.utcnow()
            db.add(conv)

            # 로그
            SendLogService(db=db).log_action(
                conversation=conv, 
                action=SendAction.send, 
                message_id=out_msg.id,
                content_sent=draft.content,
                payload_json={
                    "gmail_message_id": out_msg.gmail_message_id,
                    "airbnb_thread_id": out_thread_id,
                }
            )
            
            # 🆕 Commitment + OC 추출 (발송 후)
            try:
                import asyncio
                send_handler = SendEventHandler(db)
                # bulk에서는 동기로 처리 (이미 루프 안이므로)
                asyncio.get_event_loop().run_until_complete(
                    send_handler.on_message_sent(
                        sent_text=draft.content,
                        airbnb_thread_id=out_thread_id,
                        property_code=last_incoming.property_code or "",
                        message_id=out_msg.id,
                        conversation_id=conv.id,
                        guest_checkin_date=last_incoming.checkin_date,  # OC target_date 계산용
                    )
                )
            except Exception as ce:
                # Commitment 추출 실패해도 발송은 성공 처리
                pass

            sent_count += 1
            results.append(BulkSendResultItem(
                conversation_id=conv.id,
                result="sent",
                sent_at=datetime.utcnow(),
            ))

        except Exception as e:
            failed_count += 1
            conv.status = ConversationStatus.blocked
            db.add(conv)
            results.append(BulkSendResultItem(
                conversation_id=conv.id,
                result="failed",
                error_message=str(e),
            ))

    db.commit()

    return BulkSendResponse(
        total=len(body.conversation_ids),
        sent=sent_count,
        skipped=skipped_count,
        failed=failed_count,
        results=results,
    )