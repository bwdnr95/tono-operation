"""
Commitment: TONO의 약속 기억 저장소

핵심 원칙:
- Commitment는 Sent(발송 완료) 이벤트에서만 생성된다
- LLM은 후보를 제시하고, 시스템이 확정한다
- 모든 Commitment는 provenance(근거)를 반드시 가진다
- MVP에서 scope는 THIS_CONVERSATION만 지원한다

이 테이블이 TONO의 "두뇌"이고, LLM은 "감각기관"이다.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Any

from sqlalchemy import (
    String,
    DateTime,
    Text,
    Float,
    ForeignKey,
    Index,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommitmentTopic(str, Enum):
    """
    Commitment의 주제 분류
    
    MVP에서 지원하는 토픽:
    - 체크인/체크아웃 시간 관련
    - 인원 변경
    - 무료 제공 / 추가 요금
    - 예약 변경
    """
    EARLY_CHECKIN = "early_checkin"           # 얼리 체크인 허용/불가
    LATE_CHECKOUT = "late_checkout"           # 레이트 체크아웃 허용/불가
    CHECKIN_TIME = "checkin_time"             # 체크인 시간 확정
    CHECKOUT_TIME = "checkout_time"           # 체크아웃 시간 확정
    GUEST_COUNT_CHANGE = "guest_count_change" # 인원 변경
    FREE_PROVISION = "free_provision"         # 무료 제공 (수건, 어메니티 등)
    EXTRA_FEE = "extra_fee"                   # 추가 요금 고지
    RESERVATION_CHANGE = "reservation_change" # 날짜 변경 등
    PET_POLICY = "pet_policy"                 # 반려동물 관련 약속
    SPECIAL_REQUEST = "special_request"       # 기타 특별 요청
    OTHER = "other"                           # 분류 불가


class CommitmentType(str, Enum):
    """
    Commitment의 유형
    
    - ALLOWANCE: 허용 ("가능합니다", "해드릴게요")
    - PROHIBITION: 금지 ("불가합니다", "어렵습니다")
    - FEE: 금액 관련 ("추가 요금 2만원", "무료로 제공")
    - CHANGE: 변경/조정 ("날짜를 변경해드렸습니다")
    - CONDITION: 조건부 ("~하시면 가능합니다")
    """
    ALLOWANCE = "allowance"
    PROHIBITION = "prohibition"
    FEE = "fee"
    CHANGE = "change"
    CONDITION = "condition"


class CommitmentScope(str, Enum):
    """
    Commitment의 적용 범위
    
    MVP: THIS_CONVERSATION만 지원
    Future: GUEST_LIFETIME, PROPERTY_DEFAULT (Attach 이후)
    """
    THIS_CONVERSATION = "this_conversation"
    # 아래는 MVP에서 구현하지 않음 (스키마만 정의)
    # GUEST_LIFETIME = "guest_lifetime"
    # PROPERTY_DEFAULT = "property_default"


class CommitmentStatus(str, Enum):
    """
    Commitment의 상태
    
    - ACTIVE: 유효한 약속
    - SUPERSEDED: 새로운 약속으로 대체됨
    - EXPIRED: 만료됨 (체크아웃 이후 등)
    """
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class Commitment(Base):
    """
    TONO의 약속 기억 저장소
    
    이 테이블은 TONO Intelligence의 핵심이다.
    LLM은 후보를 제시하고, 시스템이 이 테이블에 확정한다.
    
    모든 Commitment는:
    1. Sent 이벤트에서만 생성된다
    2. provenance(근거)를 반드시 가진다
    3. conversation_id로 범위가 제한된다 (MVP)
    """
    __tablename__ = "commitments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # ─────────────────────────────────────────────────────────
    # 소속 정보
    # ─────────────────────────────────────────────────────────
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    airbnb_thread_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    
    property_code: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    
    # ─────────────────────────────────────────────────────────
    # Commitment 핵심 필드
    # ─────────────────────────────────────────────────────────
    topic: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # CommitmentTopic.value
    
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # CommitmentType.value
    
    # 약속의 구체적 내용 (구조화된 데이터)
    # 예: {"allowed": true, "time": "14:00", "fee": 0}
    # 예: {"allowed": false, "reason": "당일 예약 있음"}
    # 예: {"amount": 20000, "currency": "KRW", "description": "얼리체크인 추가요금"}
    value: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    
    # 약속 유효 시점 (있는 경우)
    # 예: 체크인 날짜, 특정 시간 등
    effective_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # 적용 범위 (MVP: this_conversation만)
    scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CommitmentScope.THIS_CONVERSATION.value,
    )
    
    # 상태
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CommitmentStatus.ACTIVE.value,
        index=True,
    )
    
    # ─────────────────────────────────────────────────────────
    # Provenance (근거 추적) - TONO의 신뢰 기반
    # ─────────────────────────────────────────────────────────
    # 이 약속의 근거가 된 발송 메시지
    provenance_message_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("incoming_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # 근거 문장 원문 (LLM이 추출한 문장)
    provenance_text: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    
    # LLM 추출 신뢰도 (0~1)
    extraction_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    
    # ─────────────────────────────────────────────────────────
    # 메타 정보
    # ─────────────────────────────────────────────────────────
    # 대체된 경우, 새로운 commitment ID
    superseded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        # conversation 내에서 같은 topic의 active commitment는 하나만
        # (새 약속이 오면 기존 것은 SUPERSEDED로 변경)
        Index(
            "ix_commitments_conversation_topic_status",
            "conversation_id",
            "topic",
            "status",
        ),
        Index(
            "ix_commitments_thread_id",
            "airbnb_thread_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Commitment(id={self.id}, "
            f"topic={self.topic}, type={self.type}, "
            f"status={self.status})>"
        )
    
    def to_dict(self) -> dict[str, Any]:
        """LLM context나 API 응답용 dict 변환"""
        return {
            "id": str(self.id),
            "topic": self.topic,
            "type": self.type,
            "value": self.value,
            "provenance_text": self.provenance_text,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def to_llm_context(self) -> str:
        """LLM에게 전달할 컨텍스트 문자열"""
        type_label = {
            "allowance": "허용",
            "prohibition": "금지",
            "fee": "요금",
            "change": "변경",
            "condition": "조건부",
        }.get(self.type, self.type)
        
        topic_label = {
            "early_checkin": "얼리체크인",
            "late_checkout": "레이트체크아웃",
            "checkin_time": "체크인시간",
            "checkout_time": "체크아웃시간",
            "guest_count_change": "인원변경",
            "free_provision": "무료제공",
            "extra_fee": "추가요금",
            "reservation_change": "예약변경",
            "pet_policy": "반려동물",
            "special_request": "특별요청",
        }.get(self.topic, self.topic)
        
        return f"[{topic_label}] {type_label}: {self.provenance_text}"


class RiskSignal(Base):
    """
    Risk Signal: Commitment 충돌 등 위험 신호
    
    이 테이블은 Draft 생성 시 호스트에게 보여줄 경고를 저장한다.
    
    LLM이 후보를 제시하고, ConflictDetector(규칙 기반)가 최종 판정한다.
    """
    __tablename__ = "risk_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Risk 유형
    # - commitment_conflict: 기존 약속과 충돌
    # - ambiguous_amount: 금액 표현 모호
    # - policy_violation: 숙소 정책 위반 가능성
    # - safety_concern: 안전 관련 우려
    signal_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    
    # 심각도: low / medium / high / critical
    severity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="medium"
    )
    
    # 경고 메시지 (호스트에게 보여줄 문구)
    message: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    
    # 관련 Commitment ID (충돌인 경우)
    related_commitment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("commitments.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # 관련 Draft Reply ID
    related_draft_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("draft_replies.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # 상세 정보 (디버깅/분석용)
    details: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    
    # 해결 여부
    resolved: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # 해결한 사람 (human) 또는 시스템
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index(
            "ix_risk_signals_conversation_resolved",
            "conversation_id",
            "resolved",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RiskSignal(id={self.id}, "
            f"type={self.signal_type}, severity={self.severity}, "
            f"resolved={self.resolved})>"
        )
