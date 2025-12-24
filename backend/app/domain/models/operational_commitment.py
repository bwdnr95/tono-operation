"""
Operational Commitment (OC) 도메인 모델

운영 액션 누락 시 CS 사고로 이어질 수 있는 Commitment 추적 레이어

설계 원칙:
- Commitment에서 파생되지만 독립적으로 추적
- Staff Notification의 기준 엔티티
- "언제 이행해야 하는가"를 추적
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Boolean,
    Integer,
    DateTime,
    Date,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base


# ─────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────

class OCTopic(str, Enum):
    """OC Topic - 자동 생성 허용/제한 구분"""
    # 자동 생성 허용 (MVP)
    early_checkin = "early_checkin"
    follow_up = "follow_up"
    facility_issue = "facility_issue"
    
    # 자동 생성 제한 (운영자 확정 필요)
    refund_check = "refund_check"
    payment = "payment"
    compensation = "compensation"
    
    @classmethod
    def auto_create_allowed(cls) -> set[str]:
        """자동 생성 허용 topic"""
        return {cls.early_checkin.value, cls.follow_up.value, cls.facility_issue.value}
    
    @classmethod
    def requires_confirmation(cls) -> set[str]:
        """운영자 확정 필요 topic"""
        return {cls.refund_check.value, cls.payment.value, cls.compensation.value}


class OCTargetTimeType(str, Enum):
    """이행 시점 명확성"""
    explicit = "explicit"  # 명확한 시점 있음 (target_date 필수)
    implicit = "implicit"  # 시점 불명확 (즉시 노출)


class OCStatus(str, Enum):
    """OC 상태"""
    pending = "pending"              # 대기 중 (미처리)
    done = "done"                    # 완료 (운영 액션 수행됨)
    resolved = "resolved"            # 해소됨 (이행 불필요)
    suggested_resolve = "suggested_resolve"  # 자동 해소 제안 (운영자 확정 필요)


class OCResolutionReason(str, Enum):
    """해소 사유"""
    guest_cancelled = "guest_cancelled"  # 게스트가 철회
    superseded = "superseded"            # 새 약속으로 대체됨
    host_confirmed = "host_confirmed"    # 호스트가 완료 확인


class OCPriority(str, Enum):
    """Staff Notification 우선순위 (즉시성 기준)"""
    immediate = "immediate"  # 🔴 지금 처리해야 함
    upcoming = "upcoming"    # 🟡 D-1 준비 필요
    pending = "pending"      # ⚪ 대기 (implicit 중 여유 있는 것)


# ─────────────────────────────────────────────────────────────
# SQLAlchemy Model
# ─────────────────────────────────────────────────────────────

class OperationalCommitment(Base):
    """
    Operational Commitment 테이블
    
    운영 액션이 필요하거나, 시점을 놓치면 CS 사고로 이어질 수 있는 약속
    """
    __tablename__ = "operational_commitments"
    
    # PK
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 관계
    commitment_id = Column(PGUUID(as_uuid=True), ForeignKey("commitments.id", ondelete="SET NULL"), nullable=True)
    conversation_id = Column(PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    provenance_message_id = Column(Integer, ForeignKey("incoming_messages.id", ondelete="SET NULL"), nullable=True)
    
    # 내용
    topic = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    evidence_quote = Column(Text, nullable=False)
    
    # 이행 시점
    target_time_type = Column(String(32), nullable=False, default=OCTargetTimeType.implicit.value)
    target_date = Column(Date, nullable=True)  # explicit일 때만 값 존재
    
    # 상태
    status = Column(String(32), nullable=False, default=OCStatus.pending.value)
    resolution_reason = Column(String(32), nullable=True)
    resolution_evidence = Column(Text, nullable=True)  # 해소 제안 근거 (게스트 메시지 등)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(64), nullable=True)  # "system" | "host" | host_id
    
    # 메타
    extraction_confidence = Column(Float, nullable=False, default=0.0)
    is_candidate_only = Column(Boolean, nullable=False, default=False)  # 운영자 확정 대기
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<OC {self.id} topic={self.topic} status={self.status}>"
    
    # ─────────────────────────────────────────────────────────
    # 비즈니스 로직
    # ─────────────────────────────────────────────────────────
    
    def calculate_priority(self, today: date, guest_checkin_date: Optional[date] = None) -> OCPriority:
        """
        Staff Notification 우선순위 계산
        
        규칙:
        1. 체류 중 / 오늘 체크인 → Immediate
        2. explicit + today >= target_date → Immediate
        3. explicit + today == target_date - 1 → Upcoming
        4. implicit → Immediate (바로 노출)
        """
        # 체류 중 또는 오늘 체크인
        if guest_checkin_date and guest_checkin_date <= today:
            return OCPriority.immediate
        
        if self.target_time_type == OCTargetTimeType.explicit.value and self.target_date:
            days_until = (self.target_date - today).days
            
            if days_until <= 0:
                return OCPriority.immediate
            elif days_until == 1:
                return OCPriority.upcoming
            else:
                return OCPriority.pending
        
        # implicit → 즉시 노출
        return OCPriority.immediate
    
    def should_show_in_notification(self, today: date, guest_checkin_date: Optional[date] = None) -> bool:
        """
        Staff Notification에 노출해야 하는지 판단
        
        규칙:
        1. status가 pending/suggested_resolve만 노출
        2. explicit: D-1부터 노출
        3. implicit: 즉시 노출
        4. 체류 중: 즉시 노출
        """
        # 완료/해소된 것은 미노출
        if self.status in (OCStatus.done.value, OCStatus.resolved.value):
            return False
        
        # 운영자 확정 대기 중인 candidate는 별도 처리
        if self.is_candidate_only:
            return True  # 확정 요청으로 노출
        
        # 체류 중
        if guest_checkin_date and guest_checkin_date <= today:
            return True
        
        # explicit: D-1부터
        if self.target_time_type == OCTargetTimeType.explicit.value and self.target_date:
            days_until = (self.target_date - today).days
            return days_until <= 1
        
        # implicit: 즉시
        return True
    
    def mark_done(self, by: str = "host") -> None:
        """완료 처리"""
        self.status = OCStatus.done.value
        self.resolved_at = datetime.utcnow()
        self.resolved_by = by
        self.updated_at = datetime.utcnow()
    
    def mark_resolved(self, reason: OCResolutionReason, by: str = "system", evidence: str = None) -> None:
        """해소 처리"""
        self.status = OCStatus.resolved.value
        self.resolution_reason = reason.value
        self.resolution_evidence = evidence
        self.resolved_at = datetime.utcnow()
        self.resolved_by = by
        self.updated_at = datetime.utcnow()
    
    def suggest_resolve(self, reason: OCResolutionReason, evidence: str = None) -> None:
        """자동 해소 제안 (운영자 확정 필요)"""
        self.status = OCStatus.suggested_resolve.value
        self.resolution_reason = reason.value
        self.resolution_evidence = evidence
        self.updated_at = datetime.utcnow()
    
    def confirm_suggested_resolve(self, by: str = "host") -> None:
        """suggested_resolve 확정"""
        if self.status != OCStatus.suggested_resolve.value:
            raise ValueError("Only suggested_resolve can be confirmed")
        
        self.status = OCStatus.resolved.value
        self.resolved_at = datetime.utcnow()
        self.resolved_by = by
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """API 응답용 dict 변환"""
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "commitment_id": str(self.commitment_id) if self.commitment_id else None,
            "topic": self.topic,
            "description": self.description,
            "evidence_quote": self.evidence_quote,
            "target_time_type": self.target_time_type,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "status": self.status,
            "resolution_reason": self.resolution_reason,
            "resolution_evidence": self.resolution_evidence,
            "is_candidate_only": self.is_candidate_only,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ─────────────────────────────────────────────────────────────
# Dataclass (서비스 레이어용)
# ─────────────────────────────────────────────────────────────

@dataclass
class OCCandidate:
    """
    LLM이 추출한 OC 후보
    
    이 구조체는 LLM → 시스템 전달용이며,
    시스템이 확정 여부를 판단한다.
    """
    topic: str
    description: str
    evidence_quote: str
    confidence: float
    target_time_type: str = OCTargetTimeType.implicit.value
    target_date: Optional[date] = None
    
    def requires_confirmation(self) -> bool:
        """운영자 확정이 필요한 topic인지"""
        return self.topic in OCTopic.requires_confirmation()
    
    def is_auto_create_allowed(self) -> bool:
        """자동 생성 허용 topic인지"""
        return self.topic in OCTopic.auto_create_allowed()


@dataclass
class StaffNotificationItem:
    """
    Staff Notification UI에 표시할 항목
    """
    oc_id: UUID
    conversation_id: UUID
    airbnb_thread_id: str
    
    # 내용
    topic: str
    description: str
    evidence_quote: str
    
    # 우선순위
    priority: OCPriority
    
    # 게스트 정보
    guest_name: Optional[str] = None
    checkin_date: Optional[date] = None
    checkout_date: Optional[date] = None
    
    # 숙소 정보 (Dashboard용)
    property_code: Optional[str] = None
    property_name: Optional[str] = None
    
    # 상태
    status: str = OCStatus.pending.value
    resolution_reason: Optional[str] = None
    resolution_evidence: Optional[str] = None  # 해소 제안 근거 (게스트 메시지)
    is_candidate_only: bool = False
    
    # 시점
    target_time_type: str = OCTargetTimeType.implicit.value
    target_date: Optional[date] = None
    
    created_at: Optional[datetime] = None
