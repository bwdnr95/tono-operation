"""
CommitmentRepository: Commitment 테이블 접근 레이어

이 레포지토리는 TONO Layer의 일부다.
- 약속의 저장/조회/상태 변경
- 모든 쓰기 작업은 Sent 이벤트를 통해서만 발생해야 함
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, and_, update
from sqlalchemy.orm import Session

from app.domain.models.commitment import (
    Commitment,
    CommitmentStatus,
    CommitmentTopic,
    CommitmentType,
    CommitmentScope,
    RiskSignal,
)


class CommitmentRepository:
    """
    Commitment 저장소
    
    핵심 원칙:
    - Commitment는 Sent 이벤트에서만 생성된다
    - 같은 topic의 새 약속이 오면 기존 것은 SUPERSEDED
    - 모든 조회는 ACTIVE 상태만 기본으로 반환
    """
    
    def __init__(self, db: Session) -> None:
        self._db = db
    
    # ─────────────────────────────────────────────────────────
    # 조회 메서드
    # ─────────────────────────────────────────────────────────
    
    def get_by_id(self, commitment_id: uuid.UUID) -> Optional[Commitment]:
        """ID로 Commitment 조회"""
        return self._db.get(Commitment, commitment_id)
    
    def get_active_by_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> List[Commitment]:
        """
        Conversation의 모든 ACTIVE Commitment 조회
        
        LLM context에 포함시키거나, Conflict Detection에 사용
        """
        stmt = (
            select(Commitment)
            .where(
                and_(
                    Commitment.conversation_id == conversation_id,
                    Commitment.status == CommitmentStatus.ACTIVE.value,
                )
            )
            .order_by(Commitment.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    def get_active_by_thread_id(
        self,
        airbnb_thread_id: str,
    ) -> List[Commitment]:
        """
        airbnb_thread_id로 모든 ACTIVE Commitment 조회
        
        Conversation이 아직 없을 때도 사용 가능
        """
        stmt = (
            select(Commitment)
            .where(
                and_(
                    Commitment.airbnb_thread_id == airbnb_thread_id,
                    Commitment.status == CommitmentStatus.ACTIVE.value,
                )
            )
            .order_by(Commitment.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    def get_active_by_topic(
        self,
        conversation_id: uuid.UUID,
        topic: CommitmentTopic | str,
    ) -> Optional[Commitment]:
        """
        특정 topic의 ACTIVE Commitment 조회
        
        Conflict Detection에서 사용:
        - 새 약속이 들어올 때 기존 약속 확인
        """
        topic_value = topic.value if isinstance(topic, CommitmentTopic) else topic
        
        stmt = (
            select(Commitment)
            .where(
                and_(
                    Commitment.conversation_id == conversation_id,
                    Commitment.topic == topic_value,
                    Commitment.status == CommitmentStatus.ACTIVE.value,
                )
            )
            .order_by(Commitment.created_at.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()
    
    # ─────────────────────────────────────────────────────────
    # 생성 메서드
    # ─────────────────────────────────────────────────────────
    
    def create(
        self,
        *,
        conversation_id: uuid.UUID,
        airbnb_thread_id: str,
        property_code: str,
        topic: CommitmentTopic | str,
        type: CommitmentType | str,
        value: dict,
        provenance_text: str,
        provenance_message_id: Optional[int] = None,
        extraction_confidence: float = 0.0,
        effective_at: Optional[datetime] = None,
    ) -> Commitment:
        """
        새 Commitment 생성
        
        주의: 이 메서드는 CommitmentService를 통해서만 호출되어야 함
        직접 호출하면 Conflict Detection을 우회하게 됨
        """
        topic_value = topic.value if isinstance(topic, CommitmentTopic) else topic
        type_value = type.value if isinstance(type, CommitmentType) else type
        
        commitment = Commitment(
            conversation_id=conversation_id,
            airbnb_thread_id=airbnb_thread_id,
            property_code=property_code,
            topic=topic_value,
            type=type_value,
            value=value,
            provenance_text=provenance_text,
            provenance_message_id=provenance_message_id,
            extraction_confidence=extraction_confidence,
            effective_at=effective_at,
            scope=CommitmentScope.THIS_CONVERSATION.value,
            status=CommitmentStatus.ACTIVE.value,
        )
        
        self._db.add(commitment)
        self._db.flush()
        
        return commitment
    
    # ─────────────────────────────────────────────────────────
    # 상태 변경 메서드
    # ─────────────────────────────────────────────────────────
    
    def supersede(
        self,
        old_commitment_id: uuid.UUID,
        new_commitment_id: uuid.UUID,
    ) -> None:
        """
        기존 Commitment를 SUPERSEDED로 변경
        
        새 약속이 기존 약속을 대체할 때 사용
        """
        stmt = (
            update(Commitment)
            .where(Commitment.id == old_commitment_id)
            .values(
                status=CommitmentStatus.SUPERSEDED.value,
                superseded_by=new_commitment_id,
                updated_at=datetime.utcnow(),
            )
        )
        self._db.execute(stmt)
        self._db.flush()
    
    def expire_by_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> int:
        """
        Conversation의 모든 ACTIVE Commitment를 EXPIRED로 변경
        
        체크아웃 이후 등 대화 종료 시 사용
        """
        stmt = (
            update(Commitment)
            .where(
                and_(
                    Commitment.conversation_id == conversation_id,
                    Commitment.status == CommitmentStatus.ACTIVE.value,
                )
            )
            .values(
                status=CommitmentStatus.EXPIRED.value,
                updated_at=datetime.utcnow(),
            )
        )
        result = self._db.execute(stmt)
        self._db.flush()
        return result.rowcount


class RiskSignalRepository:
    """
    RiskSignal 저장소
    
    Conflict Detection 결과를 저장하고 조회
    """
    
    def __init__(self, db: Session) -> None:
        self._db = db
    
    def get_unresolved_by_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> List[RiskSignal]:
        """미해결 Risk Signal 조회"""
        stmt = (
            select(RiskSignal)
            .where(
                and_(
                    RiskSignal.conversation_id == conversation_id,
                    RiskSignal.resolved == False,
                )
            )
            .order_by(RiskSignal.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())
    
    def create(
        self,
        *,
        conversation_id: uuid.UUID,
        signal_type: str,
        severity: str,
        message: str,
        related_commitment_id: Optional[uuid.UUID] = None,
        related_draft_id: Optional[uuid.UUID] = None,
        details: Optional[dict] = None,
    ) -> RiskSignal:
        """새 Risk Signal 생성"""
        signal = RiskSignal(
            conversation_id=conversation_id,
            signal_type=signal_type,
            severity=severity,
            message=message,
            related_commitment_id=related_commitment_id,
            related_draft_id=related_draft_id,
            details=details or {},
        )
        
        self._db.add(signal)
        self._db.flush()
        
        return signal
    
    def resolve(
        self,
        signal_id: uuid.UUID,
        resolved_by: str = "system",
    ) -> None:
        """Risk Signal 해결 처리"""
        stmt = (
            update(RiskSignal)
            .where(RiskSignal.id == signal_id)
            .values(
                resolved=True,
                resolved_at=datetime.utcnow(),
                resolved_by=resolved_by,
            )
        )
        self._db.execute(stmt)
        self._db.flush()
