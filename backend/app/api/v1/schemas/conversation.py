from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ConversationStatus = Literal["open", "needs_review", "ready_to_send", "sent", "blocked"]
SafetyStatus = Literal["pass", "review", "block"]
Channel = Literal["gmail"]


class ConversationListItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: Channel = "gmail"
    thread_id: str
    status: ConversationStatus
    safety_status: SafetyStatus
    last_message_id: Optional[int] = None
    updated_at: datetime


class ConversationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: Channel = "gmail"
    thread_id: str
    status: ConversationStatus
    safety_status: SafetyStatus
    last_message_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ConversationMessageDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: str
    direction: Literal["incoming", "outgoing"]
    sender_actor: Literal["GUEST", "HOST", "SYSTEM", "UNKNOWN"]
    subject: Optional[str] = None
    from_email: Optional[str] = None
    received_at: datetime
    pure_guest_message: Optional[str] = None
    content: Optional[str] = None
    intent: Optional[str] = None
    intent_confidence: Optional[float] = None


class DraftReplyDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    thread_id: str
    content: str
    safety_status: SafetyStatus
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    conversation: ConversationDTO
    messages: List[ConversationMessageDTO]
    draft_reply: Optional[DraftReplyDTO] = None


class ConversationListResponse(BaseModel):
    items: List[ConversationListItemDTO]
    next_cursor: Optional[str] = None


class DraftGenerateRequest(BaseModel):
    generation_mode: Literal["llm"] = "llm"


class DraftPatchRequest(BaseModel):
    content: str


class DraftGenerateResponse(BaseModel):
    draft_reply: DraftReplyDTO


class SendPreviewResponse(BaseModel):
    conversation_id: UUID
    draft_reply_id: UUID
    safety_status: SafetyStatus
    can_send: bool
    preview_content: str
    confirm_token: str


class SendRequest(BaseModel):
    draft_reply_id: UUID
    confirm_token: str


class SendResponse(BaseModel):
    conversation_id: UUID
    sent_at: datetime
    status: Literal["sent"] = "sent"
