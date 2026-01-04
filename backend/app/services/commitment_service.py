"""
CommitmentService: TONO Layer - Commitment 관리 오케스트레이터

핵심 원칙:
- 이 서비스가 Commitment의 생명주기를 관리한다
- LLM(CommitmentExtractor)은 후보만 제시
- 충돌 판정(ConflictDetector)은 규칙 기반
- 확정(저장)은 이 서비스가 한다
- OC(Operational Commitment)는 Commitment에서 파생된다

이 서비스는 TONO Intelligence의 "두뇌" 역할을 한다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, date
from typing import List, Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from app.domain.models.commitment import (
    Commitment,
    CommitmentTopic,
    CommitmentType,
    CommitmentStatus,
    RiskSignal,
)
from app.domain.models.operational_commitment import (
    OperationalCommitment,
    OCStatus,
    OCTargetTimeType,
)
from app.repositories.commitment_repository import (
    CommitmentRepository,
    RiskSignalRepository,
)
from app.repositories.oc_repository import OCRepository
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
    
    def __init__(self, db: Session, openai_client=None) -> None:
        self._db = db
        self._commitment_repo = CommitmentRepository(db)
        self._risk_signal_repo = RiskSignalRepository(db)
        self._oc_repo = OCRepository(db)  # 🆕 OC 저장용
        self._extractor = CommitmentExtractor(openai_client=openai_client)
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
        guest_checkin_date: Optional[date] = None,  # 🆕 OC target_date 계산용
    ) -> Tuple[List[Commitment], List[RiskSignal], List[OperationalCommitment]]:
        """
        발송된 메시지에서 Commitment 추출 및 저장
        
        이 메서드는 Sent 이벤트 발생 시 호출되어야 한다.
        
        플로우:
        1. LLM으로 Commitment 후보 추출 (1회 호출)
        2. 기존 Commitment와 충돌 검사
        3. 충돌 있으면 Risk Signal 생성
        4. Commitment 저장
        5. OC 생성 조건 충족 시 OC도 생성 (Staff Alert용)
        
        Args:
            sent_text: 발송된 답변 원문
            conversation_id: 대화 ID
            airbnb_thread_id: Gmail thread ID
            property_code: 숙소 코드
            message_id: 발송 메시지 ID (provenance용)
            conversation_context: 대화 맥락 (정확도 향상용)
            guest_checkin_date: 게스트 체크인 날짜 (OC target_date 계산용)
        
        Returns:
            (생성된 Commitment 목록, 생성된 RiskSignal 목록, 생성된 OC 목록)
        """
        logger.info(
            f"COMMITMENT_SERVICE: Processing sent message for conversation={conversation_id}"
        )
        
        # 1. LLM으로 Commitment 후보 추출
        candidates = await self._extract_candidates(sent_text, conversation_context, guest_checkin_date)
        
        if not candidates:
            logger.info("COMMITMENT_SERVICE: No commitment candidates extracted")
            return [], [], []
        
        logger.info(f"COMMITMENT_SERVICE: Extracted {len(candidates)} candidates")
        
        # 2. 기존 Commitment 조회
        existing_commitments = self._commitment_repo.get_active_by_conversation(
            conversation_id
        )
        
        # 3. 충돌 검사 및 처리
        created_commitments: List[Commitment] = []
        created_signals: List[RiskSignal] = []
        created_ocs: List[OperationalCommitment] = []
        
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
                    
                    # 🆕 OC 생성 조건 확인
                    oc = self._maybe_create_oc(
                        candidate=candidate,
                        commitment=new_commitment,
                        conversation_id=conversation_id,
                        message_id=message_id,
                        guest_checkin_date=guest_checkin_date,
                    )
                    if oc:
                        created_ocs.append(oc)
                    
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
                
                # 🆕 OC 생성 조건 확인
                oc = self._maybe_create_oc(
                    candidate=candidate,
                    commitment=commitment,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    guest_checkin_date=guest_checkin_date,
                )
                if oc:
                    created_ocs.append(oc)
        
        # DB 커밋
        self._db.commit()
        
        logger.info(
            f"COMMITMENT_SERVICE: Created {len(created_commitments)} commitments, "
            f"{len(created_signals)} risk signals, {len(created_ocs)} OCs"
        )
        
        return created_commitments, created_signals, created_ocs
    
    async def _extract_candidates(
        self,
        sent_text: str,
        conversation_context: Optional[str],
        guest_checkin_date: Optional[date] = None,
    ) -> List[CommitmentCandidate]:
        """Commitment 후보 추출 (LLM + 규칙 기반 fallback)"""
        # LLM 추출 시도 (날짜 정보 전달)
        candidates = await self._extractor.extract(sent_text, conversation_context, guest_checkin_date)
        
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
    
    # ─────────────────────────────────────────────────────────
    # 6. OC (Operational Commitment) 생성
    # ─────────────────────────────────────────────────────────
    
    def _maybe_create_oc(
        self,
        *,
        candidate: CommitmentCandidate,
        commitment: Commitment,
        conversation_id: uuid.UUID,
        message_id: Optional[int],
        guest_checkin_date: Optional[date],
    ) -> Optional[OperationalCommitment]:
        """
        Commitment에서 OC 생성 여부 판단 및 생성
        
        OC 생성 조건:
        1. type이 "action_promise"인 경우 (행동 약속)
        2. topic이 민감 토픽인 경우 (refund, payment, compensation)
        
        Returns:
            생성된 OC 또는 None
        """
        # OC 생성 조건 확인
        needs_oc = self._should_create_oc(candidate)
        
        if not needs_oc:
            return None
        
        # 민감 토픽 여부 (운영자 확인 필요)
        is_sensitive = candidate.topic in CommitmentTopic.sensitive_topics()
        
        # target_date 결정
        target_date = self._resolve_target_date(
            candidate=candidate,
            guest_checkin_date=guest_checkin_date,
        )
        
        # target_time_type 결정
        target_time_type = OCTargetTimeType.explicit if candidate.target_time_type == "explicit" else OCTargetTimeType.implicit
        
        # 같은 topic의 기존 OC supersede
        self._oc_repo.supersede_by_topic(conversation_id, candidate.topic)
        
        # OC 생성
        oc = OperationalCommitment(
            id=uuid4(),
            conversation_id=conversation_id,
            commitment_id=commitment.id,  # 🔗 FK 연결
            topic=candidate.topic,
            description=candidate.value.get("description", candidate.provenance_text),
            evidence_quote=candidate.provenance_text,  # 필드명 수정
            target_date=target_date,
            target_time_type=target_time_type.value,
            status=OCStatus.pending.value,
            is_candidate_only=is_sensitive,  # 민감 토픽은 운영자 확인 필요
            provenance_message_id=message_id,  # 필드명 수정
            extraction_confidence=candidate.confidence,  # 누락 필드 추가
            created_at=datetime.utcnow(),
        )
        
        self._db.add(oc)
        
        logger.info(
            f"COMMITMENT_SERVICE: Created OC from commitment - "
            f"topic={candidate.topic}, type={candidate.type}, "
            f"is_candidate_only={is_sensitive}"
        )
        
        return oc
    
    def _should_create_oc(self, candidate: CommitmentCandidate) -> bool:
        """OC 생성 여부 판단"""
        # 1. 행동 약속 (action_promise)이면 OC 생성
        if candidate.type in CommitmentType.oc_trigger_types():
            return True
        
        # 2. 민감 토픽이면 타입 무관하게 OC 생성
        if candidate.topic in CommitmentTopic.sensitive_topics():
            return True
        
        return False
    
    def _resolve_target_date(
        self,
        candidate: CommitmentCandidate,
        guest_checkin_date: Optional[date],
    ) -> Optional[date]:
        """OC target_date 결정"""
        # LLM이 추출한 날짜가 있으면 사용
        if candidate.target_date:
            try:
                return datetime.strptime(candidate.target_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        
        # "체크인 당일" 같은 경우 guest_checkin_date 사용
        if guest_checkin_date and candidate.target_time_type == "explicit":
            # description에 "체크인" 언급이 있으면 체크인 날짜 사용
            desc = candidate.value.get("description", "").lower()
            prov = candidate.provenance_text.lower()
            if "체크인" in desc or "체크인" in prov:
                return guest_checkin_date
        
        return None
