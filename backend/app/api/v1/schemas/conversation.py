from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Enum

SafetyStatus = Literal["pass", "review", "block"]


class ConversationListItemDTO(BaseModel):
    id: UUID
    channel: str
    airbnb_thread_id: str
    property_code: Optional[str] = None  # 숙소 코드
    status: str
    safety_status: SafetyStatus
    is_read: bool = False  # 읽음/안읽음 상태
    last_message_id: Optional[int]
    updated_at: datetime
    # 게스트 정보
    guest_name: Optional[str] = None
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None
    # 예약 상태 (inquiry, awaiting_approval, confirmed, canceled 등)
    reservation_status: Optional[str] = None
    # 마지막 발송 액션 (send, auto_sent 등)
    last_send_action: Optional[str] = None


class ConversationDTO(ConversationListItemDTO):
    created_at: datetime


class ConversationMessageDTO(BaseModel):
    id: int
    airbnb_thread_id: str
    direction: str
    content: str
    created_at: datetime
    guest_name: Optional[str] = None
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None


class DraftReplyDTO(BaseModel):
    id: UUID
    conversation_id: UUID
    airbnb_thread_id: str
    content: str
    safety_status: SafetyStatus
    created_at: datetime
    updated_at: datetime


class SendActionLogDTO(BaseModel):
    id: UUID
    conversation_id: UUID
    airbnb_thread_id: str
    message_id: Optional[int]
    action: str
    created_at: datetime


class DateConflictDTO(BaseModel):
    """날짜 충돌 예약 정보"""
    guest_name: str
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None
    status: str
    reservation_code: Optional[str] = None


class DateAvailabilityDTO(BaseModel):
    """예약 가능 여부 (INQUIRY 상태일 때 표시용)"""
    available: bool
    conflicts: List[DateConflictDTO] = []


class ConversationDetailResponse(BaseModel):
    conversation: ConversationDTO
    messages: List[ConversationMessageDTO]
    draft_reply: Optional[DraftReplyDTO]
    send_logs: List[SendActionLogDTO]
    # 발송 가능 여부 (reply_to가 있는지)
    can_reply: bool = True
    # 에어비앤비 링크 (can_reply=False일 때 사용)
    airbnb_action_url: Optional[str] = None
    # 예약 가능 여부 (INQUIRY 상태일 때만 유효)
    date_availability: Optional[DateAvailabilityDTO] = None


class ConversationListResponse(BaseModel):
    items: List[ConversationListItemDTO]
    next_cursor: Optional[str]


class DraftGenerateRequest(BaseModel):
    generation_mode: Literal["llm"] = "llm"


class DraftPatchRequest(BaseModel):
    content: str
class DraftAction(str, Enum):
    send = "send"
    bulk_send = "bulk_send"

class DraftGenerateResponse(BaseModel):
    draft_reply: DraftReplyDTO


class SendRequest(BaseModel):
    draft_reply_id: UUID
    # Orchestrator가 REQUIRE_REVIEW 판정했을 때, 강제 발송 허용
    force_send: bool = False
    # Decision 확인했음을 나타내는 로그 ID
    decision_log_id: Optional[UUID] = None


class OrchestratorWarningDTO(BaseModel):
    """Orchestrator 경고 정보"""
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"


class SendResponse(BaseModel):
    conversation_id: UUID
    sent_at: Optional[datetime] = None
    status: Literal["sent", "requires_confirmation", "blocked"] = "sent"
    
    # Orchestrator 판단 결과 (requires_confirmation일 때)
    decision: Optional[str] = None
    reason_codes: Optional[List[str]] = None
    warnings: Optional[List[OrchestratorWarningDTO]] = None
    decision_log_id: Optional[UUID] = None
    
    # 충돌 정보 (있으면)
    commitment_conflicts: Optional[List[dict]] = None