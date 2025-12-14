# backend/app/api/v1/gmail_jobs.py
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.gmail_airbnb_auto_reply_job import (
    run_gmail_airbnb_auto_reply_job,
    AutoReplyJobResult,
    AutoReplyJobItem,
)

# PREVIEW 용 import
from app.adapters.gmail_airbnb import fetch_and_parse_recent_airbnb_messages
from app.services.email_ingestion_service import ingest_parsed_airbnb_messages
from app.repositories.messages import IncomingMessageRepository
from app.services.auto_reply_service import AutoReplyService


router = APIRouter(
    prefix="/jobs/gmail",
    tags=["jobs"],
)

# -------------------------------------------------------
# 1) Airbnb 자동응답 FULL JOB (기존 엔드포인트)
# -------------------------------------------------------


class GmailAirbnbAutoReplyJobRequest(BaseModel):
    """
    Airbnb 자동응답 잡 실행 요청 바디.

    - max_results: Gmail에서 최대 몇 건까지 가져올지
    - newer_than_days: 며칠 이내 메일만 볼지 (Gmail search query의 newer_than:Xd)
    - extra_query / query: Gmail search query override 용
    - force: 이미 보낸 적 있는 메시지도 다시 보낼지 여부
    """

    max_results: int = 50
    newer_than_days: int = 3
    extra_query: Optional[str] = None
    query: Optional[str] = None
    force: bool = False


class GmailAirbnbAutoReplyJobItemDTO(BaseModel):
    """
    AutoReplyJobResult 안의 AutoReplyJobItem 를
    API 응답 스키마로 래핑한 DTO.
    """

    model_config = ConfigDict(from_attributes=True)

    gmail_message_id: str
    incoming_message_id: Optional[int]
    sent: bool
    skipped: bool
    skip_reason: Optional[str] = None


class GmailAirbnbAutoReplyJobResponse(BaseModel):
    total_parsed: int
    total_ingested: int
    total_target_messages: int
    total_sent: int
    total_skipped_already_sent: int
    total_skipped_no_message: int
    items: List[GmailAirbnbAutoReplyJobItemDTO]

def enum_to_str(value: Any) -> Optional[str]:
    """
    내부 Enum / IntEnum / 기타 값을 항상 문자열로 변환.
    - Enum 이면 .name 사용 (예: MessageIntent.GENERAL_QUESTION → "GENERAL_QUESTION")
    - 그 외엔 str(...)로 강제 캐스팅
    """
    if value is None:
        return None

    # Python Enum 계열이면 name 우선
    if isinstance(value, Enum):
        return value.name

    # Enum 아닌데 value 속성만 있는 특이 케이스 대비
    inner = getattr(value, "value", value)
    return str(inner)


@router.post(
    "/airbnb/auto-reply",
    response_model=GmailAirbnbAutoReplyJobResponse,
)
def run_airbnb_auto_reply_job(
    body: GmailAirbnbAutoReplyJobRequest,
    db: Session = Depends(get_db),
) -> GmailAirbnbAutoReplyJobResponse:
    """
    Gmail → Airbnb → IncomingMessage 인제스트 + 자동응답 발송 + 로그 기록까지
    한 번에 실행하는 잡.

    - 운영자가 수동으로 호출하거나
    - cron / scheduler 에서 주기적으로 호출하는 용도.
    """

    result: AutoReplyJobResult = run_gmail_airbnb_auto_reply_job(
        db=db,
        max_results=body.max_results,
        newer_than_days=body.newer_than_days,
        extra_query=body.extra_query,
        query=body.query,
        force=body.force,
    )

    return GmailAirbnbAutoReplyJobResponse(
        total_parsed=result.total_parsed,
        total_ingested=result.total_ingested,
        total_target_messages=result.total_target_messages,
        total_sent=result.total_sent,
        total_skipped_already_sent=result.total_skipped_already_sent,
        total_skipped_no_message=result.total_skipped_no_message,
        items=[
            GmailAirbnbAutoReplyJobItemDTO(
                gmail_message_id=item.gmail_message_id,
                incoming_message_id=item.incoming_message_id,
                sent=item.sent,
                skipped=item.skipped,
                skip_reason=item.skip_reason,
            )
            for item in result.items
        ],
    )


# -------------------------------------------------------
# 2) Airbnb 자동응답 PREVIEW JOB (발송 없이 LLM까지)
#    → /jobs/gmail/auto-reply/preview
# -------------------------------------------------------


class GmailAirbnbAutoReplyPreviewRequest(BaseModel):
    """
    PREVIEW 용 잡 파라미터.
    - max_results / newer_than_days / extra_query / query 는 full job 과 동일
    - locale: 기본 "ko"
    - use_llm: LLM 사용 여부 (지금은 True 고정으로 쓰면 됨)
    - property_code: 특정 숙소만 강제 지정하고 싶을 때 사용 가능
      (없으면 메시지에 있는 값 사용)
    - send_mode: (향후 확장용) PREVIEW / MANUAL_SEND / AUTOPILOT 등
      ※ 현재 AutoReplyService 에는 전달하지 않는다.
    """

    max_results: int = 50
    newer_than_days: int = 3
    extra_query: Optional[str] = None
    query: Optional[str] = None

    locale: str = "ko"
    use_llm: bool = True
    property_code: Optional[str] = None
    send_mode: str = "PREVIEW"


class GmailAirbnbAutoReplyPreviewItem(BaseModel):
    message_id: int
    gmail_message_id: str
    property_code: Optional[str]
    ota: Optional[str]

    guest_name: Optional[str]
    checkin_date: Optional[str]
    checkout_date: Optional[str]

    pure_guest_message: Optional[str]

    intent: Optional[str]
    fine_intent: Optional[str]

    reply_text: Optional[str]
    generation_mode: Optional[str]
    allow_auto_send: bool


class GmailAirbnbAutoReplyPreviewResponse(BaseModel):
    total_parsed: int
    total_ingested: int
    preview_items: List[GmailAirbnbAutoReplyPreviewItem]


@router.post(
    "/auto-reply/preview",
    response_model=GmailAirbnbAutoReplyPreviewResponse,
)
def run_airbnb_auto_reply_preview_job(
    body: GmailAirbnbAutoReplyPreviewRequest,
    db: Session = Depends(get_db),
) -> GmailAirbnbAutoReplyPreviewResponse:
    """
    ✅ 발송 없이, "인제스트 + Intent/FineIntent/SuggestedAction + LLM 자동응답 생성"
    까지만 수행하는 잡.

    1) Gmail에서 Airbnb 관련 메일 파싱
    2) incoming_messages 로 인제스트 (idempotent, 부수효과 함수 사용)
    3) 인제스트된 메시지 기준으로 AutoReplyService.suggest_reply_for_message_sync 호출
       → reply_text / intent / fine_intent / allow_auto_send 등 PREVIEW 데이터 반환
    """

    # 1) Gmail → Airbnb 메일 파싱
    parsed_messages = fetch_and_parse_recent_airbnb_messages(
        db=db,
        max_results=body.max_results,
        newer_than_days=body.newer_than_days,
        extra_query=body.extra_query,
        query=body.query,
    )
    total_parsed = len(parsed_messages)

    # 2) DB 인제스트 (부수효과 함수, 반환값 사용하지 않음)
    ingest_parsed_airbnb_messages(
        parsed_messages=parsed_messages,
        db=db,
    )

    msg_repo = IncomingMessageRepository(db)
    auto_reply_service = AutoReplyService(db=db)

    preview_items: List[GmailAirbnbAutoReplyPreviewItem] = []
    total_ingested = 0

    for parsed in parsed_messages:
        # ParsedInternalMessage.id == gmail_message_id 로 사용 중
        gmail_message_id = getattr(parsed, "id", None) or getattr(
            parsed, "gmail_message_id", None
        )
        if not gmail_message_id:
            continue

        msg = msg_repo.get_by_gmail_message_id(gmail_message_id)
        if msg is None:
            # 인제스트 과정에서 필터링/스킵된 케이스
            continue

        total_ingested += 1

        # AutoReplyService 의 sync wrapper 사용
        suggestion = auto_reply_service.suggest_reply_for_message_sync(
            message_id=msg.id,
            ota=msg.ota or "airbnb",
            locale=body.locale,
            property_code=body.property_code or msg.property_code,
            use_llm=body.use_llm,
            # ❌ send_mode, dry_run, force 등은 아직 서비스 시그니처에 없음
        )

        if suggestion is None:
            # Intent 결과상 답변이 불필요한 케이스 등
            continue

        # Enum / IntEnum → 항상 문자열로 변환
        intent_value: Optional[str] = enum_to_str(
            getattr(suggestion, "intent", None)
        )
        fine_intent_value: Optional[str] = enum_to_str(
            getattr(suggestion, "fine_intent", None)
        )

        preview_items.append(
            GmailAirbnbAutoReplyPreviewItem(
                message_id=msg.id,
                gmail_message_id=msg.gmail_message_id,
                property_code=msg.property_code,
                ota=msg.ota,
                guest_name=getattr(msg, "guest_name", None),
                checkin_date=str(msg.checkin_date)
                if getattr(msg, "checkin_date", None)
                else None,
                checkout_date=str(msg.checkout_date)
                if getattr(msg, "checkout_date", None)
                else None,
                pure_guest_message=msg.pure_guest_message,
                intent=intent_value,
                fine_intent=fine_intent_value,
                reply_text=suggestion.reply_text,
                generation_mode=getattr(suggestion, "generation_mode", None),
                allow_auto_send=getattr(suggestion, "allow_auto_send", False),
            )
        )

    return GmailAirbnbAutoReplyPreviewResponse(
        total_parsed=total_parsed,
        total_ingested=total_ingested,
        preview_items=preview_items,
    )
