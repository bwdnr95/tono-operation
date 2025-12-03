
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.intents import MessageIntent
from app.domain.models.message_intent_label import MessageIntentLabel
from app.services.message_intent_label_service import MessageIntentLabelService
from app.repositories.message_intent_labels import MessageIntentLabelRepository

router = APIRouter(prefix="/messages", tags=["message-intents"])


class MessageIntentLabelCreate(BaseModel):
    intent: MessageIntent


class MessageIntentLabelResponse(BaseModel):
    id: int
    message_id: int
    intent: MessageIntent
    source: str

    @classmethod
    def from_orm_label(cls, label: MessageIntentLabel) -> "MessageIntentLabelResponse":
        return cls(
            id=label.id,
            message_id=label.message_id,
            intent=label.intent,
            source=label.source.value,
        )


@router.post(
    "/{message_id}/intent-label",
    response_model=MessageIntentLabelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_human_intent_label(
    message_id: int,
    payload: MessageIntentLabelCreate,
    db: AsyncSession = Depends(get_db),
) -> MessageIntentLabelResponse:
    """
    예약실/운영자가 특정 메시지의 Intent 를 지정/수정하는 엔드포인트.

    - incoming_messages.intent / intent_confidence 를 사람 기준으로 업데이트
    - message_intent_labels 에 HUMAN 라벨 기록
    """
    service = MessageIntentLabelService(db)
    msg = await service.add_human_label_and_update_message(
        message_id=message_id,
        intent=payload.intent,
    )

    # 방금 생성된 HUMAN 라벨 하나 가져오기 (가장 최근 것)
    repo = MessageIntentLabelRepository(db)
    labels = await repo.list_labels_for_message(message_id)
    if not labels:
        raise HTTPException(status_code=500, detail="라벨 생성에 실패했습니다.")

    last_label = labels[-1]
    return MessageIntentLabelResponse.from_orm_label(last_label)


@router.get(
    "/{message_id}/intent-labels",
    response_model=List[MessageIntentLabelResponse],
)
async def list_intent_labels_for_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[MessageIntentLabelResponse]:
    """
    특정 메시지에 대해 지금까지 쌓인 Intent 라벨 히스토리 조회.
    (system / human / ml 등을 모두 포함)
    """
    repo = MessageIntentLabelRepository(db)
    labels = await repo.list_labels_for_message(message_id)
    return [MessageIntentLabelResponse.from_orm_label(l) for l in labels]