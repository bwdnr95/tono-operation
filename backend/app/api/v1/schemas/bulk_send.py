from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .conversation import ConversationListItemDTO, SafetyStatus


class BulkSendJobDTO(BaseModel):
    id: UUID
    status: Literal["pending", "completed", "partial_failed", "failed"]
    conversation_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None


class BulkSendEligibleResponse(BaseModel):
    items: List[ConversationListItemDTO]
    next_cursor: Optional[str] = None


class BulkSendPreviewRequest(BaseModel):
    conversation_ids: List[UUID]


class BulkSendPreviewItemDTO(BaseModel):
    conversation_id: UUID
    thread_id: str
    draft_reply_id: Optional[UUID] = None
    safety_status: SafetyStatus
    can_send: bool
    preview_content: Optional[str] = None
    blocked_reason: Optional[str] = None


class BulkSendPreviewResponse(BaseModel):
    job: BulkSendJobDTO
    previews: List[BulkSendPreviewItemDTO]
    confirm_token: str


class BulkSendSendRequest(BaseModel):
    confirm_token: str


class BulkSendResultItemDTO(BaseModel):
    conversation_id: UUID
    result: Literal["sent", "skipped", "failed"]
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None


class BulkSendSendResponse(BaseModel):
    job_id: UUID
    status: Literal["completed", "partial_failed", "failed"]
    results: List[BulkSendResultItemDTO]
