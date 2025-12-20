"""
CommitmentService: TONO Layer - Commitment 관리 오케스트레이터

핵심 원칙:
- 이 서비스가 Commitment의 생명주기를 관리한다
- LLM(CommitmentExtractor)은 후보만 제시
- 충돌 판정(ConflictDetector)은 규칙 기반
- 확정(저장)은 이 서비스가 한다

이 서비스는 TONO Intelligence의 "두뇌" 역할을 한다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domain.models.commitment import (
    Commitment,
    CommitmentTopic,
    CommitmentType,
    CommitmentStatus,
    RiskSignal,
)
from app.repositories.commitment_repository import (
    CommitmentRepository,
    RiskSignalRepository,
)
from app.services.commitment_extractor import (
    CommitmentExtractor,
    CommitmentCandidate,
    RuleBasedCommitmentExtractor,
)
from app.services.conflict_detector import (
    ConflictDetector,
    ConflictResult,
    ConflictSeverity,
)

logger = logging.getLogger(__name__)


class CommitmentService:
    """
    Commitment 관리 서비스
    
    역할:
    1. Sent 이벤트 시 Commitment 추출 → 검증 → 저장
    2. Draft 생성 전 기존 Commitment 제공 (LLM context용)
    3. Conflict 감지 및 Risk Signal 생성
    
    사용 패턴:
    - Sent 후: process_sent_message() 호출
    - Draft 전: get_active_commitments() 호출
    - 충돌 검사: check_draft_conflicts() 호출
    """
    
    # Confidence 임계값: 이 이상이어야 Commitment로 확정
    CONFIDENCE_THRESHOLD = 0.6
    
    def __init__(self, db: Session) -> None:
        self._db = db
        self._commitment_repo = CommitmentRepository(db)
        self._risk_signal_repo = RiskSignalRepository(db)
        self._extractor = CommitmentExtractor()
        self._rule_extractor = RuleBasedCommitmentExtractor()
        self._conflict_detector = ConflictDetector()
    
    # ─────────────────────────────────────────────────────────
    # 1. Sent 이벤트 처리 (핵심 플로우)
    # ─────────────────────────────────────────────────────────
    
    async def process_sent_message(
        self,
        *,
        sent_text: str,
        conversation_id: uuid.UUID,
        airbnb_thread_id: str,
        property_code: str,
        message_id: Optional[int] = None,
        conversation_context: Optional[str] = None,
    ) -> Tuple[List[Commitment], List[RiskSignal]]:
        """
        발송된 메시지에서 Commitment 추출 및 저장
        
        이 메서드는 Sent 이벤트 발생 시 호출되어야 한다.
        
        플로우:
        1. LLM으로 Commitment 후보 추출
        2. 기존 Commitment와 충돌 검사
        3. 충돌 있으면 Risk Signal 생성
        4. Commitment 저장 (충돌 있어도 저장, 단 경고 표시)
        
        Args:
            sent_text: 발송된 답변 원문
            conversation_id: 대화 ID
            airbnb_thread_id: Gmail thread ID
            property_code: 숙소 코드
            message_id: 발송 메시지 ID (provenance용)
            conversation_context: 대화 맥락 (정확도 향상용)
        
        Returns:
            (생성된 Commitment 목록, 생성된 RiskSignal 목록)
        """
        logger.info(
            f"COMMITMENT_SERVICE: Processing sent message for conversation={conversation_id}"
        )
        
        # 1. LLM으로 Commitment 후보 추출
        candidates = await self._extract_candidates(sent_text, conversation_context)
        
        if not candidates:
            logger.info("COMMITMENT_SERVICE: No commitment candidates extracted")
            return [], []
        
        logger.info(f"COMMITMENT_SERVICE: Extracted {len(candidates)} candidates")
        
        # 2. 기존 Commitment 조회
        existing_commitments = self._commitment_repo.get_active_by_conversation(
            conversation_id
        )
        
        # 3. 충돌 검사 및 처리
        created_commitments: List[Commitment] = []
        created_signals: List[RiskSignal] = []
        
        for candidate in candidates:
            # Confidence 필터링
            if candidate.confidence < self.CONFIDENCE_THRESHOLD:
                logger.debug(
                    f"COMMITMENT_SERVICE: Skipping low confidence candidate: "
                    f"{candidate.topic} ({candidate.confidence:.2f})"
                )
                continue
            
            # 충돌 검사
            conflict = self._conflict_detector.detect_conflict(
                candidate, existing_commitments
            )
            
            if conflict.has_conflict:
                # Risk Signal 생성
                signal = self._create_risk_signal(
                    conversation_id=conversation_id,
                    conflict=conflict,
                )
                created_signals.append(signal)
                
                logger.warning(
                    f"COMMITMENT_SERVICE: Conflict detected for {candidate.topic}: "
                    f"{conflict.message}"
                )
                
                # 기존 Commitment를 SUPERSEDED로 변경
                if conflict.existing_commitment:
                    # 새 Commitment 먼저 생성
                    new_commitment = self._create_commitment(
                        candidate=candidate,
                        conversation_id=conversation_id,
                        airbnb_thread_id=airbnb_thread_id,
                        property_code=property_code,
                        message_id=message_id,
                    )
                    created_commitments.append(new_commitment)
                    
                    # 기존 것을 SUPERSEDED로
                    self._commitment_repo.supersede(
                        old_commitment_id=conflict.existing_commitment.id,
                        new_commitment_id=new_commitment.id,
                    )
                    
                    # existing_commitments 업데이트 (다음 후보 검사용)
                    existing_commitments = [
                        c for c in existing_commitments
                        if c.id != conflict.existing_commitment.id
                    ]
                    existing_commitments.append(new_commitment)
            else:
                # 충돌 없으면 바로 저장
                commitment = self._create_commitment(
                    candidate=candidate,
                    conversation_id=conversation_id,
                    airbnb_thread_id=airbnb_thread_id,
                    property_code=property_code,
                    message_id=message_id,
                )
                created_commitments.append(commitment)
                existing_commitments.append(commitment)
        
        # DB 커밋
        self._db.commit()
        
        logger.info(
            f"COMMITMENT_SERVICE: Created {len(created_commitments)} commitments, "
            f"{len(created_signals)} risk signals"
        )
        
        return created_commitments, created_signals
    
    async def _extract_candidates(
        self,
        sent_text: str,
        conversation_context: Optional[str],
    ) -> List[CommitmentCandidate]:
        """Commitment 후보 추출 (LLM + 규칙 기반 fallback)"""
        # LLM 추출 시도
        candidates = await self._extractor.extract(sent_text, conversation_context)
        
        # LLM 실패 또는 결과 없으면 규칙 기반으로 보충
        if not candidates:
            candidates = self._rule_extractor.extract(sent_text)
        
        return candidates
    
    def _create_commitment(
        self,
        *,
        candidate: CommitmentCandidate,
        conversation_id: uuid.UUID,
        airbnb_thread_id: str,
        property_code: str,
        message_id: Optional[int],
    ) -> Commitment:
        """Commitment 생성 (Repository 위임)"""
        return self._commitment_repo.create(
            conversation_id=conversation_id,
            airbnb_thread_id=airbnb_thread_id,
            property_code=property_code,
            topic=candidate.topic,
            type=candidate.type,
            value=candidate.value,
            provenance_text=candidate.provenance_text,
            provenance_message_id=message_id,
            extraction_confidence=candidate.confidence,
        )
    
    def _create_risk_signal(
        self,
        *,
        conversation_id: uuid.UUID,
        conflict: ConflictResult,
    ) -> RiskSignal:
        """Risk Signal 생성"""
        return self._risk_signal_repo.create(
            conversation_id=conversation_id,
            signal_type="commitment_conflict",
            severity=conflict.severity.value if conflict.severity else "medium",
            message=conflict.message,
            related_commitment_id=(
                conflict.existing_commitment.id
                if conflict.existing_commitment
                else None
            ),
            details={
                "conflict_type": conflict.conflict_type.value if conflict.conflict_type else None,
                "new_topic": conflict.new_candidate.topic if conflict.new_candidate else None,
                "new_type": conflict.new_candidate.type if conflict.new_candidate else None,
            },
        )
    
    # ─────────────────────────────────────────────────────────
    # 2. Commitment 조회 (LLM Context용)
    # ─────────────────────────────────────────────────────────
    
    def get_active_commitments(
        self,
        conversation_id: uuid.UUID,
    ) -> List[Commitment]:
        """
        대화의 활성 Commitment 목록 조회
        
        Draft 생성 시 LLM context에 포함시키기 위해 호출
        """
        return self._commitment_repo.get_active_by_conversation(conversation_id)
    
    def get_active_commitments_by_thread(
        self,
        airbnb_thread_id: str,
    ) -> List[Commitment]:
        """
        airbnb_thread_id로 활성 Commitment 목록 조회
        
        Conversation이 아직 없을 때 사용
        """
        return self._commitment_repo.get_active_by_thread_id(airbnb_thread_id)
    
    def get_commitments_as_llm_context(
        self,
        conversation_id: uuid.UUID,
    ) -> str:
        """
        LLM에게 전달할 Commitment 컨텍스트 문자열 생성
        
        Returns:
            예: "[얼리체크인] 허용: 14시에 입실 가능하다고 안내드렸습니다."
        """
        commitments = self.get_active_commitments(conversation_id)
        
        if not commitments:
            return ""
        
        lines = ["[이전에 확정한 약속들]"]
        for c in commitments:
            lines.append(f"- {c.to_llm_context()}")
        
        return "\n".join(lines)
    
    # ─────────────────────────────────────────────────────────
    # 3. Draft 충돌 검사 (발송 전 검증)
    # ─────────────────────────────────────────────────────────
    
    async def check_draft_conflicts(
        self,
        *,
        draft_text: str,
        conversation_id: uuid.UUID,
        conversation_context: Optional[str] = None,
    ) -> List[ConflictResult]:
        """
        Draft가 기존 Commitment와 충돌하는지 검사
        
        발송 전에 호출하여 호스트에게 경고 표시
        
        Args:
            draft_text: 검사할 Draft 텍스트
            conversation_id: 대화 ID
            conversation_context: 대화 맥락
        
        Returns:
            충돌 결과 목록 (충돌 없으면 빈 리스트)
        """
        # Draft에서 Commitment 후보 추출
        candidates = await self._extract_candidates(draft_text, conversation_context)
        
        if not candidates:
            return []
        
        # 기존 Commitment 조회
        existing = self._commitment_repo.get_active_by_conversation(conversation_id)
        
        if not existing:
            return []
        
        # 충돌 검사
        conflicts = []
        for candidate in candidates:
            result = self._conflict_detector.detect_conflict(candidate, existing)
            if result.has_conflict:
                conflicts.append(result)
        
        return conflicts
    
    # ─────────────────────────────────────────────────────────
    # 4. Risk Signal 관리
    # ─────────────────────────────────────────────────────────
    
    def get_unresolved_signals(
        self,
        conversation_id: uuid.UUID,
    ) -> List[RiskSignal]:
        """미해결 Risk Signal 조회"""
        return self._risk_signal_repo.get_unresolved_by_conversation(conversation_id)
    
    def resolve_signal(
        self,
        signal_id: uuid.UUID,
        resolved_by: str = "human",
    ) -> None:
        """Risk Signal 해결 처리"""
        self._risk_signal_repo.resolve(signal_id, resolved_by)
        self._db.commit()
    
    # ─────────────────────────────────────────────────────────
    # 5. 대화 종료 처리
    # ─────────────────────────────────────────────────────────
    
    def expire_conversation_commitments(
        self,
        conversation_id: uuid.UUID,
    ) -> int:
        """
        대화 종료 시 모든 Commitment를 EXPIRED로 변경
        
        체크아웃 이후 등 대화가 완전히 종료될 때 호출
        
        Returns:
            만료된 Commitment 수
        """
        count = self._commitment_repo.expire_by_conversation(conversation_id)
        self._db.commit()
        return count
