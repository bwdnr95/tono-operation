# backend/app/api/v1/messages.py
from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.intents import (
    MessageActor,
    MessageActionability,
    MessageIntent,
)
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.message_intent_label import MessageIntentLabel
from app.services.message_detail_service import MessageDetailService

router = APIRouter(
    prefix="/messages",
    tags=["messages"],
)


# --- Pydantic DTOs ---


class MessageIntentLabelDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intent: MessageIntent
    source: str
    created_at: datetime


class MessageListItem(BaseModel):
    """
    메시지 리스트용 DTO.
    좌측 메시지 리스트에 필요한 정도의 정보만 포함.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    gmail_message_id: str
    thread_id: str

    subject: str | None
    from_email: str | None
    received_at: datetime

    sender_actor: MessageActor
    actionability: MessageActionability

    intent: MessageIntent | None
    intent_confidence: float | None

    # OTA / 매핑 관련 정보
    ota: str | None
    ota_listing_id: str | None
    ota_listing_name: str | None

    # TONO 내부 숙소 코드
    property_code: str | None

    # ✅ 게스트 / 숙박 정보 메타
    guest_name: str | None
    checkin_date: date | None
    checkout_date: date | None

    # ✅ 세부 Intent / 후속 액션 메타
    fine_intent: str | None
    fine_intent_confidence: float | None
    suggested_action: str | None


class MessageAutoReplyDTO(BaseModel):
    """
    메시지 상세 화면 우측 하단의 "TONO 자동응답" 박스에 들어갈 데이터 구조.
    """
    reply_text: str
    generation_mode: str | None = None
    allow_auto_send: bool
    created_at: datetime | None = None
    send_mode: str | None = None


class MessageDetail(BaseModel):
    """
    메시지 상세 조회 DTO.
    우측 상세 패널에서 사용.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    gmail_message_id: str
    thread_id: str

    subject: str | None
    from_email: str | None
    received_at: datetime

    sender_actor: MessageActor
    actionability: MessageActionability

    intent: MessageIntent | None
    intent_confidence: float | None

    # OTA / listing 정보
    ota: str | None
    ota_listing_id: str | None
    ota_listing_name: str | None

    # TONO 내부 숙소 코드
    property_code: str | None

    # ✅ 게스트 / 숙박 정보 메타
    guest_name: str | None
    checkin_date: date | None
    checkout_date: date | None

    # 본문
    text_body: str | None
    html_body: str | None
    pure_guest_message: str | None

    # ✅ Fine-grained intent / 후속 액션 메타
    fine_intent: str | None
    fine_intent_confidence: float | None
    fine_intent_reasons: str | None
    suggested_action: str | None
    allow_auto_send: bool | None

    # Intent 라벨 히스토리
    labels: List[MessageIntentLabelDTO]

    # ✅ 최신 자동응답 로그 (없을 수 있음)
    auto_reply: MessageAutoReplyDTO | None = None


# --- Helpers ---


def _to_list_item(msg: IncomingMessage) -> MessageListItem:
    return MessageListItem(
        id=msg.id,
        gmail_message_id=msg.gmail_message_id,
        thread_id=msg.thread_id,
        subject=msg.subject,
        from_email=msg.from_email,
        received_at=msg.received_at,
        sender_actor=msg.sender_actor,
        actionability=msg.actionability,
        intent=msg.intent,
        intent_confidence=msg.intent_confidence,
        ota=msg.ota,
        ota_listing_id=msg.ota_listing_id,
        ota_listing_name=msg.ota_listing_name,
        property_code=msg.property_code,
        # ✅ 새 필드 매핑
        guest_name=msg.guest_name,
        checkin_date=msg.checkin_date,
        checkout_date=msg.checkout_date,
        fine_intent=msg.fine_intent,
        fine_intent_confidence=msg.fine_intent_confidence,
        suggested_action=msg.suggested_action,
    )


def _to_detail(
    msg: IncomingMessage,
    labels: List[MessageIntentLabel],
) -> MessageDetail:
    return MessageDetail(
        id=msg.id,
        gmail_message_id=msg.gmail_message_id,
        thread_id=msg.thread_id,
        subject=msg.subject,
        from_email=msg.from_email,
        received_at=msg.received_at,
        sender_actor=msg.sender_actor,
        actionability=msg.actionability,
        intent=msg.intent,
        intent_confidence=msg.intent_confidence,
        ota=msg.ota,
        ota_listing_id=msg.ota_listing_id,
        ota_listing_name=msg.ota_listing_name,
        property_code=msg.property_code,
        # ✅ 게스트 / 숙박 메타
        guest_name=msg.guest_name,
        checkin_date=msg.checkin_date,
        checkout_date=msg.checkout_date,
        # ⚠️ DB에서는 raw text/html을 저장하지 않으므로 항상 None
        text_body=None,
        html_body=None,
        # 우리가 실제로 쓰는 건 이 필드
        pure_guest_message=msg.pure_guest_message,
        # ✅ fine intent / 후속 액션 메타
        fine_intent=msg.fine_intent,
        fine_intent_confidence=msg.fine_intent_confidence,
        fine_intent_reasons=msg.fine_intent_reasons,
        suggested_action=msg.suggested_action,
        allow_auto_send=msg.allow_auto_send,
        labels=[
            MessageIntentLabelDTO(
                id=l.id,
                intent=l.intent,
                source=l.source.value,
                created_at=l.created_at,
            )
            for l in labels
        ],
    )


# --- Routes ---


@router.get(
    "",
    response_model=List[MessageListItem],
    status_code=status.HTTP_200_OK,
)
def list_messages(
    *,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sender_actor: MessageActor | None = Query(
        default=None,
        description="필터: 발신자 유형 (게스트/호스트/시스템 등)",
    ),
    actionability: MessageActionability | None = Query(
        default=None,
        description="필터: 답장 필요 여부 등",
    ),
    intent: MessageIntent | None = Query(
        default=None,
        description="필터: Intent (CHECKIN_QUESTION 등)",
    ),
    property_code: str | None = Query(
        default=None,
        description="필터: 특정 숙소(property_code)에 속한 메시지만 보기",
    ),
    ota: str | None = Query(
        default=None,
        description="필터: 특정 OTA (airbnb 등)",
    ),
    include_system: bool = Query(
        default=False,
        description=(
            "True면 시스템 알림/호스트/답장 불필요 메시지도 포함.\n"
            "기본 False일 때는 게스트 + NEEDS_REPLY 만 반환."
        ),
    ),
) -> List[MessageListItem]:
    """
    메시지 리스트 조회.

    - 기본 정렬: 최근 수신순(received_at DESC)
    - 기본 동작: 게스트(sender_actor=GUEST) + 답장 필요(actionability=NEEDS_REPLY) 메시지만 반환
    - include_system=true 이거나 sender_actor/actionability를 명시적으로 넘기면
      그 값에 맞게 필터링
    """

    stmt = select(IncomingMessage)

    # --- sender_actor 필터 ---
    if sender_actor is not None:
        stmt = stmt.where(IncomingMessage.sender_actor == sender_actor)
    elif not include_system:
        # 기본값: 게스트 메시지만
        stmt = stmt.where(IncomingMessage.sender_actor == MessageActor.GUEST)

    # --- actionability 필터 ---
    if actionability is not None:
        stmt = stmt.where(IncomingMessage.actionability == actionability)
    elif not include_system:
        # 기본값: 답장이 필요한 메시지만
        stmt = stmt.where(
            IncomingMessage.actionability == MessageActionability.NEEDS_REPLY
        )

    # --- 기타 필터 ---
    if intent is not None:
        stmt = stmt.where(IncomingMessage.intent == intent)
    if property_code is not None:
        stmt = stmt.where(IncomingMessage.property_code == property_code)
    if ota is not None:
        stmt = stmt.where(IncomingMessage.ota == ota)

    stmt = stmt.order_by(IncomingMessage.received_at.desc())
    stmt = stmt.offset(offset).limit(limit)

    messages = db.execute(stmt).scalars().all()
    return [_to_list_item(m) for m in messages]


@router.get(
    "/{message_id}",
    response_model=MessageDetail,
    status_code=status.HTTP_200_OK,
)
def get_message_detail(
    *,
    message_id: int,
    db: Session = Depends(get_db),
) -> MessageDetail:
    """
    메시지 단건 상세 조회.
    + 최신 자동응답 로그(auto_reply_logs) 1건까지 포함.
    """

    service = MessageDetailService(db)
    result = service.get_detail(message_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    msg = result["message"]
    auto_reply = result["latest_log"]

    # message_id 기준 Intent 라벨 히스토리 조회
    stmt = (
        select(MessageIntentLabel)
        .where(MessageIntentLabel.message_id == message_id)
        .order_by(MessageIntentLabel.created_at.desc())
    )
    labels = db.execute(stmt).scalars().all()

    detail = _to_detail(msg, labels)

    # ----------------------------
    # 자동응답 로그 결합
    # ----------------------------
    if auto_reply:
        detail.auto_reply = MessageAutoReplyDTO(
            reply_text=auto_reply.reply_text,
            generation_mode=auto_reply.generation_mode,
            allow_auto_send=auto_reply.allow_auto_send,
            created_at=auto_reply.created_at,
            send_mode=auto_reply.send_mode,
        )
    else:
        detail.auto_reply = None

    return detail
