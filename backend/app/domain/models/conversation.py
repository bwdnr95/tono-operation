# backend/app/domain/models/conversation.py
"""
Conversation 도메인 모델 (v3 - Outcome Label 지원)

변경사항:
- DraftReply에 outcome_label, human_override JSONB 컬럼 추가
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import DateTime, ForeignKey, String, Text, Enum as SAEnum, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base




def _enum_values(e: type[enum.Enum]) -> list[str]:
    return [m.value for m in e]


class ConversationChannel(str, enum.Enum):
    gmail = "gmail"
    airbnb_dm = "airbnb_dm"
    manual = "manual"


class ConversationStatus(str, enum.Enum):
    new = "new"
    pending = "pending"
    needs_review = "needs_review"
    ready_to_send = "ready_to_send"
    sent = "sent"
    blocked = "blocked"
    complete = "complete"


class SafetyStatus(str, enum.Enum):
    pass_ = "pass"
    review = "review"
    block = "block"


class SendAction(str, enum.Enum):
    send = "send"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    channel: Mapped[ConversationChannel] = mapped_column(
        SAEnum(
            ConversationChannel,
            name="conversation_channel",
            values_callable=_enum_values,
            create_constraint=True,
            native_enum=False,
        ),
        nullable=False,
        default=ConversationChannel.gmail,
    )

    airbnb_thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    last_message_id: Mapped[int | None] = mapped_column(nullable=True)

    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(
            ConversationStatus,
            name="conversation_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ConversationStatus.new,
        index=True,
    )

    safety_status: Mapped[SafetyStatus] = mapped_column(
        SAEnum(
            SafetyStatus,
            name="conversation_safety_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SafetyStatus.pass_,
        index=True,
    )

    property_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # 마지막 메시지 시간 (NOT NULL)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    draft_replies: Mapped[List["DraftReply"]] = relationship("DraftReply", back_populates="conversation")
    send_logs: Mapped[List["SendActionLog"]] = relationship("SendActionLog", back_populates="conversation")


class DraftReply(Base):
    """
    초안 응답 (v5)
    
    변경사항:
    - v3: outcome_label, human_override 추가
    - v4: original_content, is_edited 추가 (수정 이력 추적)
    - v5: guest_message_snapshot 추가 (Learning Agent용)
    """
    __tablename__ = "draft_replies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )

    airbnb_thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # ===== v4 추가: 원본 LLM 응답 보존 =====
    original_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # ===== v5 추가: 게스트 메시지 스냅샷 (Learning Agent용) =====
    # Draft 생성 시점의 게스트 메시지를 저장하여 정확한 쌍 분석 가능
    guest_message_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)

    safety_status: Mapped[SafetyStatus] = mapped_column(
        SAEnum(
            SafetyStatus,
            name="draft_reply_safety_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SafetyStatus.pass_,
        index=True,
    )

    # ===== v3 추가: Outcome Label =====
    # 구조: {
    #   response_outcome: string,
    #   operational_outcome: string[],
    #   safety_outcome: string,
    #   quality_outcome: string,
    #   used_faq_keys: string[],
    #   used_profile_fields: string[],
    #   rule_applied: string[],
    #   evidence_quote: string | null
    # }
    outcome_label: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )

    # 운영자 오버라이드 기록
    # 구조: {
    #   applied: boolean,
    #   reason: string,
    #   actor: string,
    #   timestamp: string
    # }
    human_override: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="draft_replies")


class SendActionLog(Base):
    __tablename__ = "send_action_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    airbnb_thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    property_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False, default="system")

    message_id: Mapped[int | None] = mapped_column(nullable=True)

    action: Mapped[SendAction] = mapped_column(
        SAEnum(
            SendAction,
            name="send_action_log_action",
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )

    content_sent: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # DB에 NOT NULL로 있어서 빈 객체라도 넣어야 함
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="send_logs")
