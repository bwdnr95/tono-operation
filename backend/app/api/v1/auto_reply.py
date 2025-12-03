from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auto_reply_service import AutoReplyService

router = APIRouter(
    prefix="/messages",
    tags=["auto_reply"],
)


# --- Pydantic Schemas ---


class AutoReplyRequest(BaseModel):
    """
    자동응답 제안 요청 바디.

    - ota: Airbnb, Booking 등 OTA 종류 (선택)
    - locale: 응답 언어 ("ko", "en" 등)
    - property_code: 숙소 코드 (PropertyProfile.property_code)
    - use_llm: LLM 사용 여부 (False이면 템플릿/기본 fallback만 사용)
    """

    ota: str | None = Field(default=None, description="OTA provider code (e.g. airbnb)")
    locale: str | None = Field(default="ko", description="Response locale (e.g. ko, en)")
    property_code: str | None = Field(
        default=None,
        description="Property code / listing ID for loading PropertyProfile",
    )
    use_llm: bool = Field(
        default=True,
        description="Whether to use LLM with context. If false, only template/fallback is used.",
    )


class AutoReplySuggestionResponse(BaseModel):
    """
    AutoReplyService.AutoReplySuggestion 을 API 응답 형태로 변환한 모델.
    """

    model_config = ConfigDict(from_attributes=True)

    message_id: int
    intent: str
    intent_confidence: float
    reply_text: str
    template_id: int | None
    generation_mode: str


# --- Router Handlers ---


@router.post(
    "/{message_id}/auto-reply",
    response_model=AutoReplySuggestionResponse,
    status_code=status.HTTP_200_OK,
)
async def suggest_auto_reply_for_message(
    message_id: int,
    body: AutoReplyRequest,
    db: Session = Depends(get_db),
) -> AutoReplySuggestionResponse:
    """
    특정 message_id 에 대한 자동응답 문장 제안.

    - 메시지 Intent 분류 (없으면 자동 분류)
    - PropertyProfile / IncomingMessage / Intent 기반 컨텍스트 생성
    - LLM + 템플릿을 사용해 최종 reply_text 생성
    """

    service = AutoReplyService(session=db)

    suggestion = await service.suggest_reply_for_message(
        message_id=message_id,
        ota=body.ota,
        locale=body.locale,
        property_code=body.property_code,
        use_llm=body.use_llm,
    )

    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    return AutoReplySuggestionResponse(
        message_id=suggestion.message_id,
        intent=suggestion.intent.name,
        intent_confidence=suggestion.intent_confidence,
        reply_text=suggestion.reply_text,
        template_id=suggestion.template_id,
        generation_mode=suggestion.generation_mode,
    )
