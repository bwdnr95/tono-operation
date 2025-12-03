from __future__ import annotations

from datetime import datetime
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
from app.domain.intents.types import IntentLabelSource

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

    # 본문
    text_body: str | None
    html_body: str | None
    pure_guest_message: str | None

    # Intent 라벨 히스토리
    labels: List[MessageIntentLabelDTO]


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
        text_body=msg.text_body,
        html_body=msg.html_body,
        pure_guest_message=msg.pure_guest_message,
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
    "/",
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
) -> List[MessageListItem]:
    """
    메시지 리스트 조회.

    - 기본 정렬: 최근 수신순(received_at DESC)
    - 간단한 필터: sender_actor, actionability, intent, property_code, ota
    """

    stmt = select(IncomingMessage).order_by(IncomingMessage.received_at.desc())

    if sender_actor is not None:
        stmt = stmt.where(IncomingMessage.sender_actor == sender_actor)
    if actionability is not None:
        stmt = stmt.where(IncomingMessage.actionability == actionability)
    if intent is not None:
        stmt = stmt.where(IncomingMessage.intent == intent)
    if property_code is not None:
        stmt = stmt.where(IncomingMessage.property_code == property_code)
    if ota is not None:
        stmt = stmt.where(IncomingMessage.ota == ota)

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
    - 본문(text/html/pure_guest_message)
    - OTA/리스팅 정보
    - property_code
    - Intent 라벨 히스토리 포함
    """

    msg: IncomingMessage | None = db.get(IncomingMessage, message_id)
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    # message_id 기준 Intent 라벨 히스토리 조회
    stmt = (
        select(MessageIntentLabel)
        .where(MessageIntentLabel.message_id == message_id)
        .order_by(MessageIntentLabel.created_at.desc())
    )
    labels = db.execute(stmt).scalars().all()

    return _to_detail(msg, labels)
