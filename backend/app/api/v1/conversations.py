from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.adapters.gmail_send_adapter import GmailSendAdapter
from app.adapters.gmail_airbnb import fetch_and_parse_recent_airbnb_messages
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
from app.domain.models.reservation_info import ReservationInfo
from app.services.auto_reply_service import AutoReplyService
from app.services.email_ingestion_service import ingest_airbnb_parsed_messages

from app.services.conversation_thread_service import (
    DraftService,
    SafetyGuardService,
    SendLogService,
    apply_safety_to_conversation,
)
from app.services.gmail_fetch_service import get_gmail_service
from app.services.send_event_handler import SendEventHandler
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
    SendRequest,
    SendResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _encode_cursor(dt: datetime, cid: UUID) -> str:
    payload = {"dt": dt.isoformat(), "id": str(cid)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    obj = json.loads(raw)
    return datetime.fromisoformat(obj["dt"]), UUID(obj["id"])


def _safety_literal(s: SafetyStatus) -> str:
    return "pass" if s == SafetyStatus.pass_ else s.value


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    channel: str = Query("gmail"),
    airbnb_thread_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    safety_status: Optional[str] = Query(None),
    is_read: Optional[bool] = Query(None, description="true=읽음, false=안읽음, null=전체"),
    updated_since: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = select(Conversation).where(Conversation.channel == ConversationChannel.gmail)

    if airbnb_thread_id:
        q = q.where(Conversation.airbnb_thread_id == airbnb_thread_id)
    if status:
        q = q.where(Conversation.status == ConversationStatus(status))
    if safety_status:
        if safety_status == "pass":
            q = q.where(Conversation.safety_status == SafetyStatus.pass_)
        else:
            q = q.where(Conversation.safety_status == SafetyStatus(safety_status))
    if is_read is not None:
        q = q.where(Conversation.is_read == is_read)
    if updated_since:
        q = q.where(Conversation.updated_at >= datetime.fromisoformat(updated_since))

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

    # 각 conversation의 게스트 정보 조회 (reservation_info 기준)
    items = []
    for r in rows:
        # reservation_info에서 예약 정보 조회
        reservation = db.execute(
            select(ReservationInfo)
            .where(ReservationInfo.airbnb_thread_id == r.airbnb_thread_id)
        ).scalar_one_or_none()
        
        items.append(ConversationListItemDTO(
            id=r.id,
            channel=r.channel.value,
            airbnb_thread_id=r.airbnb_thread_id,
            property_code=r.property_code or (reservation.property_code if reservation else None),
            status=r.status.value,
            safety_status=_safety_literal(r.safety_status),
            is_read=r.is_read,
            last_message_id=r.last_message_id,
            updated_at=r.updated_at,
            guest_name=reservation.guest_name if reservation else None,
            checkin_date=str(reservation.checkin_date) if reservation and reservation.checkin_date else None,
            checkout_date=str(reservation.checkout_date) if reservation and reservation.checkout_date else None,
        ))
    
    return ConversationListResponse(items=items, next_cursor=next_cursor)


# ============================================================
# 읽음/안읽음 처리
# ============================================================

class MarkReadResponse(BaseModel):
    conversation_id: UUID
    is_read: bool


@router.post("/{conversation_id}/mark-read", response_model=MarkReadResponse)
def mark_conversation_read(
    conversation_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Conversation을 읽음 처리
    
    - Send 완료 시 자동 호출됨
    - 또는 "처리완료" 버튼 클릭 시 호출
    """
    conv = db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    ).scalar_one_or_none()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv.is_read = True
    conv.updated_at = datetime.utcnow()
    db.commit()
    
    return MarkReadResponse(conversation_id=conv.id, is_read=True)


@router.post("/{conversation_id}/mark-unread", response_model=MarkReadResponse)
def mark_conversation_unread(
    conversation_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Conversation을 안읽음 처리
    
    - 새 게스트 메시지 도착 시 자동 호출됨
    - 또는 수동으로 안읽음 표시
    """
    conv = db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    ).scalar_one_or_none()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv.is_read = False
    conv.updated_at = datetime.utcnow()
    db.commit()
    
    return MarkReadResponse(conversation_id=conv.id, is_read=False)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(conversation_id: UUID, db: Session = Depends(get_db)):
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = db.execute(
        select(IncomingMessage)
        .where(IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id)
        .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
    ).scalars().all()

    draft = DraftService(db).get_latest(conversation_id=conv.id)

    # reservation_info에서 예약 정보 조회
    reservation = db.execute(
        select(ReservationInfo)
        .where(ReservationInfo.airbnb_thread_id == conv.airbnb_thread_id)
    ).scalar_one_or_none()

    from app.domain.models.conversation import SendActionLog
    logs = db.execute(
        select(SendActionLog)
        .where(SendActionLog.conversation_id == conv.id)
        .order_by(desc(SendActionLog.created_at))
        .limit(20)
    ).scalars().all()

    return ConversationDetailResponse(
        conversation=ConversationDTO(
            id=conv.id,
            channel=conv.channel.value,
            airbnb_thread_id=conv.airbnb_thread_id,
            property_code=conv.property_code or (reservation.property_code if reservation else None),
            status=conv.status.value,
            safety_status=_safety_literal(conv.safety_status),
            is_read=conv.is_read,
            last_message_id=conv.last_message_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            guest_name=reservation.guest_name if reservation else None,
            checkin_date=str(reservation.checkin_date) if reservation and reservation.checkin_date else None,
            checkout_date=str(reservation.checkout_date) if reservation and reservation.checkout_date else None,
        ),
        messages=[
            ConversationMessageDTO(
                id=m.id,
                airbnb_thread_id=m.airbnb_thread_id,
                direction=m.direction.value if m.direction else "incoming",
                content=m.content or m.pure_guest_message or "",
                created_at=m.received_at,
                guest_name=m.guest_name,
                checkin_date=str(m.checkin_date) if m.checkin_date else None,
                checkout_date=str(m.checkout_date) if m.checkout_date else None,
            )
            for m in msgs
        ],
        draft_reply=DraftReplyDTO(
            id=draft.id,
            conversation_id=draft.conversation_id,
            airbnb_thread_id=draft.airbnb_thread_id,
            content=draft.content,
            safety_status=_safety_literal(draft.safety_status),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        ) if draft else None,
        send_logs=[
            {
                "id": log.id,
                "conversation_id": log.conversation_id,
                "airbnb_thread_id": log.airbnb_thread_id,
                "message_id": log.message_id,
                "action": log.action.value,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    )


@router.post("/{conversation_id}/draft-reply/generate", response_model=DraftGenerateResponse)
async def generate_draft(conversation_id: UUID, body: DraftGenerateRequest, db: Session = Depends(get_db)):
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = db.execute(
        select(IncomingMessage)
        .where(IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id)
        .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
    ).scalars().all()

    last_guest_msg = None
    for m in reversed(msgs):
        if m.direction == MessageDirection.incoming and m.sender_actor == MessageActor.GUEST:
            last_guest_msg = m
            break

    if not last_guest_msg:
        raise HTTPException(status_code=400, detail="No guest message found in thread")

    auto_reply_service = AutoReplyService(db=db)
    suggestion = await auto_reply_service.suggest_reply_for_message(
        message_id=last_guest_msg.id,
        ota=last_guest_msg.ota or "airbnb",
        locale="ko",
        property_code=last_guest_msg.property_code,
        use_llm=True,
    )

    if suggestion is None:
        content = DraftService(db).generate_draft(airbnb_thread_id=conv.airbnb_thread_id)
    else:
        content = suggestion.reply_text

    guard = SafetyGuardService(db)
    safety, _ = guard.evaluate_text(text=content)

    draft = DraftService(db).upsert_latest(conversation=conv, content=content, safety=safety)
    apply_safety_to_conversation(conv, safety)
    db.add(conv)
    db.commit()

    return DraftGenerateResponse(
        draft_reply=DraftReplyDTO(
            id=draft.id,
            conversation_id=draft.conversation_id,
            airbnb_thread_id=draft.airbnb_thread_id,
            content=draft.content,
            safety_status=_safety_literal(draft.safety_status),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
    )


@router.patch("/{conversation_id}/draft-reply", response_model=DraftGenerateResponse)
def patch_draft(conversation_id: UUID, body: DraftPatchRequest, db: Session = Depends(get_db)):
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    guard = SafetyGuardService(db)
    safety, _ = guard.evaluate_text(text=body.content)

    draft = DraftService(db).upsert_latest(
        conversation=conv, 
        content=body.content, 
        safety=safety,
        is_user_edit=True,  # ✅ v4: 사용자 수정으로 처리
    )
    apply_safety_to_conversation(conv, safety)
    db.add(conv)
    db.commit()

    return DraftGenerateResponse(
        draft_reply=DraftReplyDTO(
            id=draft.id,
            conversation_id=draft.conversation_id,
            airbnb_thread_id=draft.airbnb_thread_id,
            content=draft.content,
            safety_status=_safety_literal(draft.safety_status),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
    )


@router.post("/{conversation_id}/send", response_model=SendResponse)
async def send_reply(conversation_id: UUID, body: SendRequest, db: Session = Depends(get_db)):
    """
    Conversation 단건 발송.
    - Draft → Send 직행 (Preview 없음)
    - confirm_token 없음
    """
    conv = db.execute(select(Conversation).where(Conversation.id == conversation_id)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # ready_to_send 또는 blocked(재시도) 상태에서만 발송 가능
    if conv.status not in (ConversationStatus.ready_to_send, ConversationStatus.blocked):
        raise HTTPException(status_code=400, detail=f"Conversation status is {conv.status.value}. Must be ready_to_send or blocked.")

    draft = DraftService(db).get_latest(conversation_id=conv.id)
    if not draft or str(draft.id) != str(body.draft_reply_id):
        raise HTTPException(status_code=400, detail="Draft reply not found or mismatch")
    
    # airbnb_thread_id invariant 검증
    if draft.airbnb_thread_id != conv.airbnb_thread_id:
        raise HTTPException(status_code=400, detail="Draft airbnb_thread_id mismatch with conversation")
    
    if draft.safety_status == SafetyStatus.block or conv.safety_status == SafetyStatus.block:
        raise HTTPException(status_code=400, detail="Safety status is block. Cannot send.")

    last_incoming = db.execute(
        select(IncomingMessage)
        .where(IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id, IncomingMessage.direction == MessageDirection.incoming)
        .order_by(desc(IncomingMessage.received_at), desc(IncomingMessage.id))
        .limit(1)
    ).scalar_one_or_none()
    
    if not last_incoming:
        conv.status = ConversationStatus.blocked
        db.add(conv)
        db.commit()
        raise HTTPException(status_code=400, detail="No incoming message found")

    # reply_to가 없으면 발송 불가
    if not last_incoming.reply_to:
        conv.status = ConversationStatus.blocked
        db.add(conv)
        db.commit()
        raise HTTPException(status_code=400, detail="Reply-To not found. Cannot send reply.")

    gmail_service = get_gmail_service(db)
    
    # Gmail threadId 조회 (airbnb_thread_id와 다름!)
    gmail_thread_id = None
    if last_incoming.gmail_message_id:
        try:
            # suffix 제거 (_0, _1 등 - 같은 이메일에서 여러 메시지 분리 저장 시 사용)
            clean_gmail_id = last_incoming.gmail_message_id.split('_')[0]
            gmail_msg = gmail_service.users().messages().get(
                userId="me", 
                id=clean_gmail_id,
                format="minimal"
            ).execute()
            gmail_thread_id = gmail_msg.get("threadId")
        except Exception as e:
            logger.warning(f"Failed to get Gmail threadId: {e}")
    
    if not gmail_thread_id:
        conv.status = ConversationStatus.blocked
        db.add(conv)
        db.commit()
        raise HTTPException(status_code=400, detail="Gmail thread ID not found. Cannot send reply.")
    
    sender = GmailSendAdapter(service=gmail_service)
    try:
        resp = sender.send_reply(
            gmail_thread_id=gmail_thread_id,
            to_email=last_incoming.reply_to,
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
    out_gmail_thread_id = resp.get("threadId")  # Gmail thread ID (참고용)
    
    # outgoing 메시지는 기존 airbnb_thread_id로 저장 (연결 유지)
    out_msg = IncomingMessage(
        gmail_message_id=str(out_gmail_message_id),
        gmail_thread_id=out_gmail_thread_id,  # Gmail thread ID 별도 저장
        airbnb_thread_id=conv.airbnb_thread_id,  # 기존 airbnb_thread_id 유지!
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

    # airbnb_thread_id는 변경하지 않음! (기존 메시지들과 연결 유지)
    conv.last_message_id = out_msg.id
    conv.status = ConversationStatus.sent
    conv.is_read = True  # 발송 완료 = 읽음 처리
    conv.updated_at = datetime.utcnow()
    db.add(conv)

    SendLogService(db=db).log_action(
        conversation=conv, 
        action=SendAction.send, 
        message_id=out_msg.id,
        content_sent=draft.content,
        payload_json={
            "gmail_message_id": out_msg.gmail_message_id,
            "gmail_thread_id": out_gmail_thread_id,  # Gmail thread ID (참고용)
            "airbnb_thread_id": conv.airbnb_thread_id,
            # ✅ v4: 수정 이력 추적
            "safety_status": str(draft.safety_status.value),
            "is_edited": draft.is_edited,
            "original_content": draft.original_content if draft.is_edited else None,
        }
    )

    db.commit()
    
    # 🆕 Commitment + OC 추출 (발송 후 비동기 처리)
    try:
        import asyncio
        send_handler = SendEventHandler(db)
        
        # 대화 맥락 생성 (최근 게스트 메시지)
        conversation_context = None
        if last_incoming.pure_guest_message:
            conversation_context = f"게스트 요청: {last_incoming.pure_guest_message[:500]}"
        
        asyncio.create_task(
            send_handler.on_message_sent(
                sent_text=draft.content,
                airbnb_thread_id=conv.airbnb_thread_id,
                property_code=last_incoming.property_code or "",
                message_id=out_msg.id,
                conversation_id=conv.id,
                guest_checkin_date=last_incoming.checkin_date,  # OC target_date 계산용
                conversation_context=conversation_context,  # 🆕 대화 맥락 추가
            )
        )
    except Exception as e:
        # Commitment 추출 실패해도 발송은 성공
        logger.warning(f"Commitment extraction failed: {e}")

    return SendResponse(conversation_id=conv.id, sent_at=datetime.utcnow(), status="sent")


# ============================================================
# Gmail Ingest (Conversation 기반)
# ============================================================

class GmailIngestRequest(BaseModel):
    max_results: int = 50
    newer_than_days: int = 3


class GmailIngestConversationItem(BaseModel):
    conversation_id: str
    airbnb_thread_id: str
    status: str
    draft_content: Optional[str] = None
    guest_message: Optional[str] = None


class GmailIngestResponse(BaseModel):
    total_parsed: int
    total_conversations: int
    conversations: List[GmailIngestConversationItem]


@router.post("/ingest-gmail", response_model=GmailIngestResponse)
async def ingest_gmail_and_generate_drafts(
    body: GmailIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Gmail 인제스트 + Conversation 생성 + Draft 생성

    1) Gmail에서 Airbnb 메일 파싱
    2) incoming_messages 저장 + conversations 생성/업데이트
    3) 각 Conversation에 대해 LLM Draft 생성
    """
    # 1) Gmail 파싱
    parsed_messages = fetch_and_parse_recent_airbnb_messages(
        db=db,
        max_results=body.max_results,
        newer_than_days=body.newer_than_days,
    )
    total_parsed = len(parsed_messages)

    # 2) DB 인제스트 (incoming_messages + conversations 생성)
    await ingest_airbnb_parsed_messages(db=db, parsed_messages=parsed_messages)
    db.commit()

    # 3) airbnb_thread_id 목록 추출 (중복 제거)
    thread_ids = set()
    for parsed in parsed_messages:
        tid = getattr(parsed, "airbnb_thread_id", None)
        if tid:
            thread_ids.add(tid)

    # 4) 각 Conversation에 대해 Draft 생성
    result_items: List[GmailIngestConversationItem] = []
    auto_reply_service = AutoReplyService(db=db)
    draft_service = DraftService(db)
    guard = SafetyGuardService(db)

    for airbnb_thread_id in thread_ids:
        # Conversation 조회
        conv = db.execute(
            select(Conversation).where(
                Conversation.channel == ConversationChannel.gmail,
                Conversation.airbnb_thread_id == airbnb_thread_id,
            )
        ).scalar_one_or_none()

        if not conv:
            continue

        # ✅ 이미 처리된 conversation은 스킵 (sent, ready_to_send)
        if conv.status in [ConversationStatus.sent]:
            result_items.append(GmailIngestConversationItem(
                conversation_id=str(conv.id),
                airbnb_thread_id=airbnb_thread_id,
                status="skipped_already_sent",
            ))
            continue

        # ✅ 이미 draft가 있는 경우 스킵 (LLM 중복 호출 방지)
        existing_draft = draft_service.get_latest(conversation_id=conv.id)
        if existing_draft and existing_draft.content:
            result_items.append(GmailIngestConversationItem(
                conversation_id=str(conv.id),
                airbnb_thread_id=airbnb_thread_id,
                status="skipped_draft_exists",
                draft_content=existing_draft.content[:200] + "..." if len(existing_draft.content) > 200 else existing_draft.content,
            ))
            continue

        # 마지막 GUEST 메시지 찾기
        msgs = db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
            .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
        ).scalars().all()

        last_guest_msg = None
        for m in reversed(msgs):
            if m.direction == MessageDirection.incoming and m.sender_actor == MessageActor.GUEST:
                last_guest_msg = m
                break

        if not last_guest_msg:
            # GUEST 메시지 없으면 스킵
            result_items.append(GmailIngestConversationItem(
                conversation_id=str(conv.id),
                airbnb_thread_id=airbnb_thread_id,
                status="skipped_no_guest_message",
            ))
            continue

        # LLM으로 Draft 생성 (새 conversation만)
        try:
            suggestion = await auto_reply_service.suggest_reply_for_message(
                message_id=last_guest_msg.id,
                locale="ko",
                property_code=last_guest_msg.property_code,
            )
            
            if suggestion and suggestion.reply_text:
                content = suggestion.reply_text
                outcome_label = suggestion.outcome_label.to_dict() if suggestion.outcome_label else None
            else:
                content = draft_service.generate_draft(airbnb_thread_id=airbnb_thread_id)
                outcome_label = None
        except Exception as e:
            logger.warning(f"LLM draft generation failed: {e}")
            content = draft_service.generate_draft(airbnb_thread_id=airbnb_thread_id)
            outcome_label = None

        # Safety 평가
        safety, _ = guard.evaluate_text(text=content)

        # Draft 저장 (Outcome Label 포함)
        draft_service.upsert_latest(
            conversation=conv,
            content=content,
            safety=safety,
            outcome_label=outcome_label,
        )

        # Conversation 상태 업데이트
        apply_safety_to_conversation(conv, safety)
        db.add(conv)

        result_items.append(GmailIngestConversationItem(
            conversation_id=str(conv.id),
            airbnb_thread_id=airbnb_thread_id,
            status=conv.status.value,
            draft_content=content[:200] + "..." if len(content) > 200 else content,
            guest_message=last_guest_msg.pure_guest_message[:100] if last_guest_msg.pure_guest_message else None,
        ))

    db.commit()

    return GmailIngestResponse(
        total_parsed=total_parsed,
        total_conversations=len(result_items),
        conversations=result_items,
    )