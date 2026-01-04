"""
TONO Orchestrator Core - Domain Models

Orchestrator는 TONO의 판단 엔진이다.
모든 메시지 처리에 대해 Decision을 내리고, 그 근거를 기록한다.

핵심 원칙:
1. 모든 판단은 Decision + ReasonCodes로 표현된다
2. 모든 판단은 DecisionLog에 영구 기록된다
3. 사람의 수정/승인도 기록된다 (HumanAction)
4. 누적된 데이터로 자동화 영역을 확장한다

A2A (Agent-to-Agent) 구조:
- ResponderAgent: 답변 생성
- AuditorAgent: 발송 가능 여부 판단
- RetrospectiveAgent: 패턴 분석 및 정책 추천
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    String,
    DateTime,
    Text,
    Float,
    Boolean,
    Integer,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ═══════════════════════════════════════════════════════════════════
# Enums - Decision 관련
# ═══════════════════════════════════════════════════════════════════

class Decision(str, Enum):
    """
    Orchestrator의 최종 판단
    
    AUTO_SEND: 자동 발송 가능 (검증된 패턴)
    SUGGEST_SEND: 발송 권장 (인간 확인 후 클릭만)
    REQUIRE_REVIEW: 검토 필요 (내용 확인 권장)
    REQUIRE_EDIT: 수정 필요 (특정 부분 수정 요구)
    BLOCK: 발송 차단 (위험 감지)
    """
    AUTO_SEND = "auto_send"
    SUGGEST_SEND = "suggest_send"
    REQUIRE_REVIEW = "require_review"
    REQUIRE_EDIT = "require_edit"
    BLOCK = "block"


class ReasonCode(str, Enum):
    """
    Decision의 근거 코드 (정규화)
    
    각 ReasonCode는 Decision에 영향을 미치는 요인.
    여러 ReasonCode가 조합되어 최종 Decision이 결정됨.
    """
    # ─────────────────────────────────────────────────────
    # 긍정 요인 (AUTO_SEND / SUGGEST_SEND 방향)
    # ─────────────────────────────────────────────────────
    FAQ_GROUNDED = "faq_grounded"                    # FAQ 기반 답변
    PROFILE_GROUNDED = "profile_grounded"            # PropertyProfile 기반
    COMMITMENT_CONSISTENT = "commitment_consistent"  # 기존 약속과 일치
    SAFE_CONTENT = "safe_content"                    # 안전한 내용
    HIGH_CONFIDENCE = "high_confidence"              # LLM 신뢰도 높음
    SIMILAR_APPROVED = "similar_approved"            # 유사 메시지가 승인된 이력
    SIMPLE_INQUIRY = "simple_inquiry"                # 단순 문의 (체크인 시간 등)
    CLOSING_MESSAGE = "closing_message"              # 종료 인사
    
    # ─────────────────────────────────────────────────────
    # 부정 요인 (REQUIRE_REVIEW / BLOCK 방향)
    # ─────────────────────────────────────────────────────
    COMMITMENT_CONFLICT = "commitment_conflict"      # 기존 약속과 충돌
    SENSITIVE_TOPIC = "sensitive_topic"              # 민감 토픽 (환불, 보상 등)
    HIGH_RISK_KEYWORDS = "high_risk_keywords"        # 위험 키워드 감지
    LOW_CONFIDENCE = "low_confidence"                # LLM 신뢰도 낮음
    MISSING_INFORMATION = "missing_information"      # 정보 부족
    AMBIGUOUS_RESPONSE = "ambiguous_response"        # 모호한 응답
    NEW_COMMITMENT = "new_commitment"                # 새로운 약속 생성
    FINANCIAL_MENTION = "financial_mention"          # 금액 언급
    PERSONAL_INFO = "personal_info"                  # 개인정보 포함
    POLICY_VIOLATION = "policy_violation"            # 정책 위반 가능성
    COMPLAINT_DETECTED = "complaint_detected"        # 불만 감지
    SAFETY_CONCERN = "safety_concern"                # 안전 우려 (부상, 사고 등)
    
    # ─────────────────────────────────────────────────────
    # 중립/정보성
    # ─────────────────────────────────────────────────────
    FIRST_MESSAGE = "first_message"                  # 첫 메시지 (패턴 없음)
    EDITED_BY_HUMAN = "edited_by_human"              # 인간이 수정함
    HUMAN_OVERRIDE = "human_override"                # 인간이 판단 오버라이드


class HumanAction(str, Enum):
    """
    인간이 취한 액션
    
    Decision에 대한 인간의 반응을 기록.
    이 데이터가 자동화 확대의 근거가 됨.
    """
    APPROVED_AS_IS = "approved_as_is"        # 수정 없이 승인
    APPROVED_WITH_EDIT = "approved_with_edit"  # 수정 후 승인
    REJECTED = "rejected"                     # 거부 (발송 안 함)
    ESCALATED = "escalated"                   # 상위 담당자에게 전달
    PENDING = "pending"                       # 아직 액션 없음


class AutomationEligibility(str, Enum):
    """
    자동화 적합성 판정 (Retrospective Agent가 판단)
    """
    ELIGIBLE = "eligible"              # 자동화 가능
    CONDITIONAL = "conditional"        # 조건부 가능
    NOT_ELIGIBLE = "not_eligible"      # 자동화 부적합
    NEEDS_MORE_DATA = "needs_more_data"  # 데이터 더 필요


# ═══════════════════════════════════════════════════════════════════
# SQLAlchemy Models
# ═══════════════════════════════════════════════════════════════════

class DecisionLog(Base):
    """
    모든 Orchestrator 판단의 영구 기록
    
    이 테이블이 TONO 자동화의 핵심 자산이다.
    - 모든 Decision + ReasonCodes 기록
    - 인간의 후속 액션 기록
    - Retrospective 분석의 원천 데이터
    """
    __tablename__ = "decision_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # ─────────────────────────────────────────────────────
    # 연결 정보
    # ─────────────────────────────────────────────────────
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    draft_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("draft_replies.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    airbnb_thread_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    
    property_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    
    # ─────────────────────────────────────────────────────
    # 입력 컨텍스트 (판단 시점의 스냅샷)
    # ─────────────────────────────────────────────────────
    guest_message: Mapped[str] = mapped_column(Text, nullable=False)
    draft_content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 판단에 사용된 컨텍스트 (FAQ, Commitments 등)
    context_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    
    # ─────────────────────────────────────────────────────
    # Orchestrator 판단 결과
    # ─────────────────────────────────────────────────────
    decision: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # Decision enum value
    
    # 판단 근거 (복수 가능)
    reason_codes: Mapped[List[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list
    )
    
    # 상세 판단 정보 (LLM 응답 원문 등)
    decision_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    
    # 판단 신뢰도 (0.0 ~ 1.0)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    
    # ─────────────────────────────────────────────────────
    # 인간 후속 액션
    # ─────────────────────────────────────────────────────
    human_action: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )  # HumanAction enum value
    
    human_action_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    human_actor: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # 액션을 취한 사람 ID
    
    # 인간이 수정한 경우, 수정된 내용
    edited_content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    
    # 인간의 코멘트 (왜 수정했는지 등)
    human_comment: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    
    # ─────────────────────────────────────────────────────
    # 결과 (실제로 어떻게 됐는지)
    # ─────────────────────────────────────────────────────
    was_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    final_content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 실제 발송된 내용
    
    # ─────────────────────────────────────────────────────
    # Retrospective 분석 결과 (나중에 채워짐)
    # ─────────────────────────────────────────────────────
    automation_eligibility: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )  # AutomationEligibility enum value
    
    eligibility_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    
    pattern_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # 매칭된 패턴 ID (있으면)
    
    # ─────────────────────────────────────────────────────
    # 메타
    # ─────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, 
        default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    __table_args__ = (
        Index("ix_decision_logs_decision_human_action", "decision", "human_action"),
        Index("ix_decision_logs_property_created", "property_code", "created_at"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<DecisionLog(id={self.id}, decision={self.decision}, "
            f"human_action={self.human_action}, was_sent={self.was_sent})>"
        )
    
    def record_human_action(
        self,
        action: HumanAction,
        actor: str,
        edited_content: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> None:
        """인간 액션 기록"""
        self.human_action = action.value
        self.human_action_at = datetime.utcnow()
        self.human_actor = actor
        if edited_content:
            self.edited_content = edited_content
        if comment:
            self.human_comment = comment
        self.updated_at = datetime.utcnow()
    
    def record_sent(self, final_content: str) -> None:
        """발송 완료 기록"""
        self.was_sent = True
        self.sent_at = datetime.utcnow()
        self.final_content = final_content
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """API 응답용 dict 변환"""
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "confidence": self.confidence,
            "human_action": self.human_action,
            "was_sent": self.was_sent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AutomationPattern(Base):
    """
    자동화 패턴 정의
    
    Retrospective Agent가 분석하여 생성.
    이 패턴에 매칭되면 AUTO_SEND 가능.
    """
    __tablename__ = "automation_patterns"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # 패턴 식별
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 패턴 조건
    # 예: {"message_type": "simple_inquiry", "topics": ["checkin_time", "wifi"]}
    conditions: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    
    # 적용 범위
    property_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # None이면 전체 적용
    
    # 통계
    total_matches: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    
    approved_as_is_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    
    approved_with_edit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    
    rejected_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    
    # 자동화 승인 여부
    is_auto_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    
    auto_approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    auto_approved_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # 승인한 관리자
    
    # 최소 요구 조건
    min_sample_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )
    
    min_approval_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.95
    )  # 95% 이상이면 자동화 권장
    
    # 메타
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    def __repr__(self) -> str:
        return f"<AutomationPattern(id={self.id}, name={self.name}, is_auto_approved={self.is_auto_approved})>"
    
    @property
    def approval_rate(self) -> float:
        """수정 없이 승인된 비율"""
        if self.total_matches == 0:
            return 0.0
        return self.approved_as_is_count / self.total_matches
    
    @property
    def is_eligible_for_automation(self) -> bool:
        """자동화 적합 여부"""
        return (
            self.total_matches >= self.min_sample_size and
            self.approval_rate >= self.min_approval_rate
        )
    
    def increment_match(self, human_action: HumanAction) -> None:
        """매칭 통계 업데이트"""
        self.total_matches += 1
        if human_action == HumanAction.APPROVED_AS_IS:
            self.approved_as_is_count += 1
        elif human_action == HumanAction.APPROVED_WITH_EDIT:
            self.approved_with_edit_count += 1
        elif human_action == HumanAction.REJECTED:
            self.rejected_count += 1
        self.updated_at = datetime.utcnow()


class PolicyRule(Base):
    """
    정책 규칙 정의
    
    Orchestrator가 Decision을 내릴 때 참조하는 규칙.
    관리자가 직접 설정하거나, Retrospective가 추천.
    """
    __tablename__ = "policy_rules"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # 규칙 식별
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 규칙 유형
    rule_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # "block", "review", "allow"
    
    # 조건 (JSON으로 유연하게)
    # 예: {"keywords": ["환불", "소송"], "action": "block"}
    # 예: {"topic": "early_checkin", "confidence_min": 0.8, "action": "allow"}
    conditions: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    
    # 적용되는 ReasonCode
    applies_reason_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    
    # 결과 Decision
    resulting_decision: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    
    # 우선순위 (낮을수록 먼저 평가)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100
    )
    
    # 적용 범위
    property_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # None이면 전체 적용
    
    # 상태
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    
    # 출처
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual"
    )  # "manual", "retrospective", "system"
    
    # 메타
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<PolicyRule(id={self.id}, name={self.name}, rule_type={self.rule_type})>"
