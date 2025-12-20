"""
Operational Commitment Repository

OC 데이터 접근 레이어
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from app.domain.models.operational_commitment import (
    OperationalCommitment,
    OCStatus,
    OCTargetTimeType,
    OCResolutionReason,
    OCPriority,
)


class OCRepository:
    """Operational Commitment Repository"""
    
    def __init__(self, db: Session):
        self._db = db
    
    # ─────────────────────────────────────────────────────────
    # 기본 CRUD
    # ─────────────────────────────────────────────────────────
    
    def save(self, oc: OperationalCommitment) -> OperationalCommitment:
        """저장"""
        self._db.add(oc)
        self._db.flush()
        return oc
    
    def get_by_id(self, oc_id: UUID) -> Optional[OperationalCommitment]:
        """ID로 조회"""
        return self._db.execute(
            select(OperationalCommitment).where(OperationalCommitment.id == oc_id)
        ).scalar_one_or_none()
    
    def get_by_conversation(self, conversation_id: UUID) -> List[OperationalCommitment]:
        """Conversation의 모든 OC 조회"""
        stmt = (
            select(OperationalCommitment)
            .where(OperationalCommitment.conversation_id == conversation_id)
            .order_by(OperationalCommitment.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    # ─────────────────────────────────────────────────────────
    # 상태별 조회
    # ─────────────────────────────────────────────────────────
    
    def get_pending_by_conversation(self, conversation_id: UUID) -> List[OperationalCommitment]:
        """Conversation의 pending OC 조회"""
        stmt = (
            select(OperationalCommitment)
            .where(
                OperationalCommitment.conversation_id == conversation_id,
                OperationalCommitment.status == OCStatus.pending.value,
            )
            .order_by(OperationalCommitment.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    def get_active_by_conversation(self, conversation_id: UUID) -> List[OperationalCommitment]:
        """
        Conversation의 활성 OC 조회
        - pending, suggested_resolve 상태
        """
        stmt = (
            select(OperationalCommitment)
            .where(
                OperationalCommitment.conversation_id == conversation_id,
                OperationalCommitment.status.in_([
                    OCStatus.pending.value,
                    OCStatus.suggested_resolve.value,
                ]),
            )
            .order_by(OperationalCommitment.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    def get_candidates_by_conversation(self, conversation_id: UUID) -> List[OperationalCommitment]:
        """운영자 확정 대기 중인 후보 조회"""
        stmt = (
            select(OperationalCommitment)
            .where(
                OperationalCommitment.conversation_id == conversation_id,
                OperationalCommitment.is_candidate_only == True,
            )
            .order_by(OperationalCommitment.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    # ─────────────────────────────────────────────────────────
    # Staff Notification 조회
    # ─────────────────────────────────────────────────────────
    
    def get_for_notification(
        self,
        today: date,
        property_code: Optional[str] = None,
        limit: int = 50,
    ) -> List[OperationalCommitment]:
        """
        Staff Notification에 노출할 OC 조회
        
        규칙:
        1. status = pending or suggested_resolve
        2. explicit: target_date - 1 <= today
        3. implicit: 즉시 노출
        4. is_candidate_only: 확정 요청으로 노출
        """
        # 기본 조건: 활성 상태
        base_conditions = [
            OperationalCommitment.status.in_([
                OCStatus.pending.value,
                OCStatus.suggested_resolve.value,
            ])
        ]
        
        # explicit 조건: D-1부터 노출
        # implicit 조건: 항상 노출
        time_conditions = or_(
            # implicit → 항상 노출
            OperationalCommitment.target_time_type == OCTargetTimeType.implicit.value,
            # explicit → D-1부터
            and_(
                OperationalCommitment.target_time_type == OCTargetTimeType.explicit.value,
                OperationalCommitment.target_date <= today + timedelta(days=1),
            ),
            # candidate_only → 확정 요청으로 항상 노출
            OperationalCommitment.is_candidate_only == True,
        )
        
        stmt = (
            select(OperationalCommitment)
            .where(and_(*base_conditions, time_conditions))
            .order_by(
                # 우선순위 정렬: target_date 오름차순 (급한 것 먼저)
                OperationalCommitment.target_date.asc().nullsfirst(),
                OperationalCommitment.created_at.desc(),
            )
            .limit(limit)
        )
        
        return list(self._db.execute(stmt).scalars().all())
    
    # ─────────────────────────────────────────────────────────
    # 상태 변경
    # ─────────────────────────────────────────────────────────
    
    def mark_done(self, oc_id: UUID, by: str = "host") -> Optional[OperationalCommitment]:
        """완료 처리"""
        oc = self.get_by_id(oc_id)
        if oc:
            oc.mark_done(by=by)
            self._db.flush()
        return oc
    
    def mark_resolved(
        self,
        oc_id: UUID,
        reason: OCResolutionReason,
        by: str = "system",
    ) -> Optional[OperationalCommitment]:
        """해소 처리"""
        oc = self.get_by_id(oc_id)
        if oc:
            oc.mark_resolved(reason=reason, by=by)
            self._db.flush()
        return oc
    
    def suggest_resolve(
        self,
        oc_id: UUID,
        reason: OCResolutionReason,
    ) -> Optional[OperationalCommitment]:
        """자동 해소 제안"""
        oc = self.get_by_id(oc_id)
        if oc:
            oc.suggest_resolve(reason=reason)
            self._db.flush()
        return oc
    
    def confirm_suggested_resolve(
        self,
        oc_id: UUID,
        by: str = "host",
    ) -> Optional[OperationalCommitment]:
        """suggested_resolve 확정"""
        oc = self.get_by_id(oc_id)
        if oc and oc.status == OCStatus.suggested_resolve.value:
            oc.confirm_suggested_resolve(by=by)
            self._db.flush()
        return oc
    
    def confirm_candidate(self, oc_id: UUID) -> Optional[OperationalCommitment]:
        """후보를 정식 OC로 확정"""
        oc = self.get_by_id(oc_id)
        if oc and oc.is_candidate_only:
            oc.is_candidate_only = False
            oc.updated_at = datetime.utcnow()
            self._db.flush()
        return oc
    
    def reject_candidate(self, oc_id: UUID) -> Optional[OperationalCommitment]:
        """후보 거부 (삭제 또는 resolved)"""
        oc = self.get_by_id(oc_id)
        if oc and oc.is_candidate_only:
            oc.mark_resolved(reason=OCResolutionReason.host_confirmed, by="host")
            self._db.flush()
        return oc
    
    # ─────────────────────────────────────────────────────────
    # Topic 기반 조회/처리
    # ─────────────────────────────────────────────────────────
    
    def get_active_by_topic(
        self,
        conversation_id: UUID,
        topic: str,
    ) -> List[OperationalCommitment]:
        """같은 topic의 활성 OC 조회"""
        stmt = (
            select(OperationalCommitment)
            .where(
                OperationalCommitment.conversation_id == conversation_id,
                OperationalCommitment.topic == topic,
                OperationalCommitment.status.in_([
                    OCStatus.pending.value,
                    OCStatus.suggested_resolve.value,
                ]),
            )
            .order_by(OperationalCommitment.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    def supersede_by_topic(
        self,
        conversation_id: UUID,
        topic: str,
        exclude_id: Optional[UUID] = None,
    ) -> int:
        """
        같은 topic의 기존 OC를 superseded로 처리
        
        Returns:
            처리된 OC 수
        """
        existing = self.get_active_by_topic(conversation_id, topic)
        count = 0
        
        for oc in existing:
            if exclude_id and oc.id == exclude_id:
                continue
            oc.mark_resolved(reason=OCResolutionReason.superseded, by="system")
            count += 1
        
        if count > 0:
            self._db.flush()
        
        return count


# timedelta import 누락 수정
from datetime import timedelta
