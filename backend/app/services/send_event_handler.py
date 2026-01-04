"""
SendEventHandler: Sent 이벤트 후처리 핸들러

Sent 이벤트 발생 시 호출되어:
1. Commitment 추출 및 저장
2. Conflict 감지 및 Risk Signal 생성
3. Operational Commitment 생성 (Commitment에서 파생)
4. 🆕 Answer Embedding 저장 (Few-shot Learning용)

OC는 CommitmentService에서 자동 생성됨 (별도 LLM 호출 없음)

사용법:
    handler = SendEventHandler(db)
    await handler.on_message_sent(
        sent_text=reply_text,
        conversation_id=conversation_id,
        airbnb_thread_id=airbnb_thread_id,
        property_code=property_code,
        message_id=sent_message_id,
        guest_message=guest_msg,  # 🆕 Few-shot용
        was_edited=is_edited,     # 🆕 Few-shot용
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
from app.domain.models.answer_embedding import AnswerEmbedding
from app.services.commitment_service import CommitmentService
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class SendEventHandler:
    """
    Sent 이벤트 후처리 핸들러
    
    GmailOutboxService에서 메시지 발송 후 이 핸들러를 호출하면:
    - Commitment 추출 및 저장 (LLM 1회 호출)
    - Conflict 감지 및 Risk Signal 생성
    - OC 자동 생성 (action_promise 타입 또는 민감 토픽)
    
    기존 서비스 코드 변경 없이 Commitment 기능을 추가할 수 있다.
    """
    
    def __init__(self, db: Session) -> None:
        self._db = db
        
        # OpenAI 클라이언트 싱글톤 (DI)
        from app.adapters.llm_client import get_openai_client
        openai_client = get_openai_client()
        
        self._commitment_service = CommitmentService(db, openai_client=openai_client)
        self._embedding_service = EmbeddingService(db, openai_client=openai_client)
    
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
        # 🆕 Few-shot Learning용 파라미터
        guest_message: Optional[str] = None,
        was_edited: bool = False,
    ) -> Tuple[List[Commitment], List[RiskSignal], List[OperationalCommitment]]:
        """
        메시지 발송 후 Commitment + OC + Embedding 처리
        
        Args:
            sent_text: 발송된 답변 원문
            airbnb_thread_id: Gmail thread ID
            property_code: 숙소 코드
            message_id: 발송 메시지 ID (있으면)
            conversation_id: Conversation ID (없으면 airbnb_thread_id로 조회)
            conversation_context: 대화 맥락 (있으면 정확도 향상)
            guest_checkin_date: 게스트 체크인 날짜 (OC target_date 계산용)
            guest_message: 게스트 메시지 원문 (Few-shot Learning용)
            was_edited: AI 초안이 수정되었는지 여부 (Few-shot Learning용)
        
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
        
        # 🆕 Answer Embedding 저장 (Few-shot Learning용)
        if guest_message and sent_text:
            try:
                self._embedding_service.store_answer(
                    guest_message=guest_message,
                    final_answer=sent_text,
                    property_code=property_code,
                    was_edited=was_edited,
                    conversation_id=conversation_id,
                    airbnb_thread_id=airbnb_thread_id,
                )
                logger.info(
                    f"SEND_EVENT_HANDLER: Stored answer embedding for airbnb_thread_id={airbnb_thread_id}, "
                    f"was_edited={was_edited}"
                )
            except Exception as e:
                # Embedding 저장 실패해도 다른 처리는 계속 진행
                logger.warning(f"SEND_EVENT_HANDLER: Failed to store answer embedding: {e}")
        else:
            logger.debug(
                f"SEND_EVENT_HANDLER: Skipping embedding storage - "
                f"guest_message={bool(guest_message)}, sent_text={bool(sent_text)}"
            )
        
        # Commitment 추출 + OC 생성 (통합 처리, LLM 1회 호출)
        try:
            commitments, signals, ocs = await self._commitment_service.process_sent_message(
                sent_text=sent_text,
                conversation_id=conversation_id,
                airbnb_thread_id=airbnb_thread_id,
                property_code=property_code,
                message_id=message_id,
                conversation_context=conversation_context,
                guest_checkin_date=guest_checkin_date,
            )
            
            logger.info(
                f"SEND_EVENT_HANDLER: Created {len(commitments)} commitments, "
                f"{len(signals)} risk signals, {len(ocs)} OCs"
            )
            
            return commitments, signals, ocs
            
        except Exception as e:
            logger.error(
                f"SEND_EVENT_HANDLER: Failed to process sent message: {e}",
                exc_info=True,
            )
            return [], [], []
    
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
