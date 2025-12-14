from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auto_reply_service import AutoReplyService
from app.services.gmail_fetch_service import get_gmail_service
from app.services.gmail_outbox_service import GmailOutboxService
from app.domain.models.incoming_message import IncomingMessage

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


class SendAutoReplyRequest(BaseModel):
    """
    프론트에서 '자동응답 제안 받기'로 받은 reply_text를
    사람이 수정한 뒤 최종 텍스트로 보내주는 용도.
    """
    final_reply_text: str | None = None
    force: bool = False


class SendAutoReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: int
    sent: bool
    skip_reason: str | None = None
    log_id: int | None = None
    sent_at: datetime | None = None




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


@router.post(
    "/{message_id}/auto-reply/send",
    response_model=SendAutoReplyResponse,
    status_code=status.HTTP_200_OK,
)
def send_auto_reply_for_message(
    *,
    message_id: int,
    payload: SendAutoReplyRequest,
    db: Session = Depends(get_db),
) -> SendAutoReplyResponse:
    """
    단일 메시지에 대해 실제 자동응답 메일을 발송하는 엔드포인트.

    흐름:
      1) message_id 로 IncomingMessage 존재 여부 확인
      2) GmailService, AutoReplyService, GmailOutboxService 초기화
      3) GmailOutboxService.send_auto_reply_for_message(...) 호출
         - 이미 발송한 적 있으면 재발송하지 않고 skip
         - payload.final_reply_text 가 있으면 그 텍스트를 우선 사용
    """
    msg: IncomingMessage | None = db.get(IncomingMessage, message_id)
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    # Gmail 서비스 + AutoReplyService + Outbox 초기화
    gmail_service = get_gmail_service(db)
    auto_reply_service = AutoReplyService(db=db)
    outbox = GmailOutboxService(
        db=db,
        auto_reply_service=auto_reply_service,
        gmail_service=gmail_service,
    )

    # GmailOutboxService 쪽에 override_reply_text 지원이 있어야 한다.
    # 없다면, 메서드 시그니처에 optional 인자로 추가해주면 된다.
    suggestion = outbox.send_auto_reply_for_message(
        message_id=message_id,
        force=payload.force,
        override_reply_text=payload.final_reply_text,
    )

    # # send_auto_reply_for_message 가 이미 내부에서
    # # auto_reply_logs insert + allow_auto_send=False 처리한다고 가정.
    # # suggestion 객체에 log_id, sent_at, skipped 여부가 포함되어 있을 수 있음.

    # if suggestion.skipped:
    #     db.commit()
    #     return SendAutoReplyResponse(
    #         message_id=message_id,
    #         sent=False,
    #         skip_reason=suggestion.skip_reason,
    #         log_id=None,
    #         sent_at=None,
    #     )

    db.commit()
    return SendAutoReplyResponse(
        message_id=message_id,
        sent=True,
        skip_reason=None,
        log_id=getattr(suggestion, "log_id", None),
        sent_at=getattr(suggestion, "sent_at", None),
    )