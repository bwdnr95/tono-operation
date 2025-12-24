"""
SendEventHandler: Sent 이벤트 후처리 핸들러

Sent 이벤트 발생 시 호출되어:
1. Commitment 추출 및 저장
2. Conflict 감지 및 Risk Signal 생성
3. Operational Commitment 추출 및 저장

이 핸들러는 기존 코드 변경을 최소화하면서 Commitment 처리를 통합한다.

사용법:
    handler = SendEventHandler(db)
    await handler.on_message_sent(
        sent_text=reply_text,
        conversation_id=conversation_id,
        airbnb_thread_id=airbnb_thread_id,
        property_code=property_code,
        message_id=sent_message_id,
    )
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models.commitment import Commitment, RiskSignal
from app.domain.models.conversation import Conversation
from app.domain.models.operational_commitment import OperationalCommitment
from app.services.commitment_service import CommitmentService
from app.services.oc_service import OCService

logger = logging.getLogger(__name__)


class SendEventHandler:
    """
    Sent 이벤트 후처리 핸들러
    
    GmailOutboxService에서 메시지 발송 후 이 핸들러를 호출하면:
    - Commitment 추출 및 저장
    - Conflict 감지 및 Risk Signal 생성
    - Operational Commitment 추출 및 저장
    
    기존 서비스 코드 변경 없이 Commitment 기능을 추가할 수 있다.
    """
    
    def __init__(self, db: Session) -> None:
        self._db = db
        self._commitment_service = CommitmentService(db)
        self._oc_service = OCService(db)
    
    async def on_message_sent(
        self,
        *,
        sent_text: str,
        airbnb_thread_id: str,
        property_code: str,
        message_id: Optional[int] = None,
        conversation_id: Optional[uuid.UUID] = None,
        conversation_context: Optional[str] = None,
        guest_checkin_date: Optional[date] = None,
    ) -> Tuple[List[Commitment], List[RiskSignal], List[OperationalCommitment]]:
        """
        메시지 발송 후 Commitment + OC 처리
        
        Args:
            sent_text: 발송된 답변 원문
            airbnb_thread_id: Gmail thread ID
            property_code: 숙소 코드
            message_id: 발송 메시지 ID (있으면)
            conversation_id: Conversation ID (없으면 airbnb_thread_id로 조회)
            conversation_context: 대화 맥락 (있으면 정확도 향상)
            guest_checkin_date: 게스트 체크인 날짜 (OC target_date 계산용)
        
        Returns:
            (생성된 Commitment 목록, 생성된 RiskSignal 목록, 생성된 OC 목록)
        """
        logger.info(
            f"SEND_EVENT_HANDLER: Processing sent event for airbnb_thread_id={airbnb_thread_id}"
        )
        
        # conversation_id가 없으면 airbnb_thread_id로 조회
        if conversation_id is None:
            conversation = self._get_conversation_by_thread(airbnb_thread_id)
            if conversation:
                conversation_id = conversation.id
            else:
                # Conversation이 없으면 Commitment 처리 불가
                logger.warning(
                    f"SEND_EVENT_HANDLER: No conversation found for airbnb_thread_id={airbnb_thread_id}, "
                    f"skipping commitment extraction"
                )
                return [], [], []
        
        commitments = []
        signals = []
        ocs = []
        
        # 1. Commitment 추출
        try:
            commitments, signals = await self._commitment_service.process_sent_message(
                sent_text=sent_text,
                conversation_id=conversation_id,
                airbnb_thread_id=airbnb_thread_id,
                property_code=property_code,
                message_id=message_id,
                conversation_context=conversation_context,
            )
            
            logger.info(
                f"SEND_EVENT_HANDLER: Created {len(commitments)} commitments, "
                f"{len(signals)} risk signals"
            )
            
        except Exception as e:
            logger.error(
                f"SEND_EVENT_HANDLER: Failed to process commitments: {e}",
                exc_info=True,
            )
        
        # 2. Operational Commitment 추출
        try:
            ocs = await self._oc_service.process_sent_message(
                sent_text=sent_text,
                conversation_id=conversation_id,
                message_id=message_id,
                guest_checkin_date=guest_checkin_date,
                commitment_id=commitments[0].id if commitments else None,
                conversation_context=conversation_context,
            )
            
            logger.info(
                f"SEND_EVENT_HANDLER: Created {len(ocs)} operational commitments"
            )
            
        except Exception as e:
            logger.error(
                f"SEND_EVENT_HANDLER: Failed to process OCs: {e}",
                exc_info=True,
            )
        
        return commitments, signals, ocs
    
    def _get_conversation_by_thread(self, airbnb_thread_id: str) -> Optional[Conversation]:
        """airbnb_thread_id로 Conversation 조회"""
        stmt = select(Conversation).where(Conversation.airbnb_thread_id == airbnb_thread_id).limit(1)
        return self._db.execute(stmt).scalar_one_or_none()
    
    def get_active_commitments_for_draft(
        self,
        airbnb_thread_id: str,
    ) -> str:
        """
        Draft 생성 전 기존 Commitment를 LLM context로 반환
        
        ReplyContextBuilder에서 호출하여 LLM에게 기존 약속 정보 제공
        """
        conversation = self._get_conversation_by_thread(airbnb_thread_id)
        
        if not conversation:
            return ""
        
        return self._commitment_service.get_commitments_as_llm_context(conversation.id)
    
    async def check_draft_conflicts(
        self,
        *,
        draft_text: str,
        airbnb_thread_id: str,
    ) -> List[dict]:
        """
        Draft가 기존 Commitment와 충돌하는지 검사
        
        Returns:
            충돌 정보 리스트 (프론트엔드용 dict 형태)
        """
        conversation = self._get_conversation_by_thread(airbnb_thread_id)
        
        if not conversation:
            return []
        
        conflicts = await self._commitment_service.check_draft_conflicts(
            draft_text=draft_text,
            conversation_id=conversation.id,
        )
        
        # 프론트엔드용 dict 변환
        return [
            {
                "has_conflict": c.has_conflict,
                "type": c.conflict_type.value if c.conflict_type else None,
                "severity": c.severity.value if c.severity else None,
                "message": c.message,
                "existing_commitment": (
                    c.existing_commitment.to_dict() 
                    if c.existing_commitment else None
                ),
            }
            for c in conflicts
        ]
    
    def get_unresolved_risk_signals(
        self,
        airbnb_thread_id: str,
    ) -> List[dict]:
        """
        미해결 Risk Signal 조회 (프론트엔드용)
        """
        conversation = self._get_conversation_by_thread(airbnb_thread_id)
        
        if not conversation:
            return []
        
        signals = self._commitment_service.get_unresolved_signals(conversation.id)
        
        return [
            {
                "id": str(s.id),
                "type": s.signal_type,
                "severity": s.severity,
                "message": s.message,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals
        ]
