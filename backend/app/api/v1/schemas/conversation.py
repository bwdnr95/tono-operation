from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
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


class ConversationDetailResponse(BaseModel):
    conversation: ConversationDTO
    messages: List[ConversationMessageDTO]
    draft_reply: Optional[DraftReplyDTO]
    send_logs: List[SendActionLogDTO]


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


class SendResponse(BaseModel):
    conversation_id: UUID
    sent_at: datetime
    status: Literal["sent"] = "sent"