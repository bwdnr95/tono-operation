"""
Operational Commitment Service

OC 조회, 해소, Staff Notification 로직을 오케스트레이션한다.

설계 원칙:
- Conversation이 모든 기준
- 자동 발송 없음
- 애매하면 suggested_resolve

NOTE: OC 생성은 CommitmentService에서 담당 (Commitment에서 파생)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.domain.models.operational_commitment import (
    OperationalCommitment,
    OCCandidate,
    OCTopic,
    OCTargetTimeType,
    OCStatus,
    OCResolutionReason,
    OCPriority,
    StaffNotificationItem,
)
from app.domain.models.conversation import Conversation
from app.domain.models.incoming_message import IncomingMessage
from app.repositories.oc_repository import OCRepository

logger = logging.getLogger(__name__)


class OCService:
    """
    Operational Commitment Service
    
    역할:
    1. Guest/Host 메시지 기반 해소 처리
    2. Staff Notification 목록 제공
    3. OC 상태 변경 (done, resolve 등)
    
    NOTE: OC 생성은 CommitmentService._maybe_create_oc()에서 담당
    """
    
    # Confidence threshold
    MIN_CONFIDENCE = 0.7
    
    def __init__(self, db: Session, openai_client=None):
        self._db = db
        self._repo = OCRepository(db)
        # openai_client는 호환성 위해 받지만, 더 이상 사용 안 함
    
    # ─────────────────────────────────────────────────────────
    # OC 해소 (Guest 메시지 기반)
    # ─────────────────────────────────────────────────────────
    
    async def process_guest_message(
        self,
        guest_text: str,
        conversation_id: UUID,
    ) -> List[Tuple[OperationalCommitment, str]]:
        """
        Guest 메시지 기반 OC 해소 처리
        
        규칙:
        A. 명시적 철회 → 자동 resolved
        B. 모호한 해소 → suggested_resolve (단일 OC만)
        
        Returns:
            (OC, action) 튜플 리스트
            action: "resolved", "suggested_resolve", "none"
        """
        if not guest_text:
            return []
        
        active_ocs = self._repo.get_active_by_conversation(conversation_id)
        if not active_ocs:
            return []
        
        results = []
        text_lower = guest_text.lower()
        
        # A. 명시적 철회 패턴
        explicit_cancel_patterns = [
            r'안\s*해도\s*(될|돼)',
            r'필요\s*없',
            r'취소.*해.*주세요',
            r'안\s*할게요',
            r'괜찮아요.*안\s*해도',
        ]
        
        for oc in active_ocs:
            # Topic별 명시적 철회 확인
            is_explicit_cancel = False
            
            for pattern in explicit_cancel_patterns:
                if self._matches_topic_context(guest_text, oc.topic, pattern):
                    is_explicit_cancel = True
                    break
            
            if is_explicit_cancel:
                oc.mark_resolved(
                    reason=OCResolutionReason.guest_cancelled, 
                    by="system",
                    evidence=guest_text[:200],  # 게스트 메시지 저장
                )
                results.append((oc, "resolved"))
                logger.info(f"OC {oc.id} auto-resolved: guest_cancelled")
                continue
        
        # B. 모호한 해소 패턴 (단일 OC만)
        vague_resolve_patterns = [
            r'괜찮아요',
            r'해결.*됐',
            r'잘\s*됐',
            r'감사합니다',  # 감사 + 해결 맥락
        ]
        
        remaining_ocs = [oc for oc, action in results if action == "none"] if results else active_ocs
        
        # 단일 OC + 모호한 해소 → suggested_resolve
        if len(remaining_ocs) == 1:
            for pattern in vague_resolve_patterns:
                import re
                if re.search(pattern, guest_text):
                    oc = remaining_ocs[0]
                    if oc.status == OCStatus.pending.value:
                        oc.suggest_resolve(
                            reason=OCResolutionReason.guest_cancelled,
                            evidence=guest_text[:200],  # 게스트 메시지 저장
                        )
                        results.append((oc, "suggested_resolve"))
                        logger.info(f"OC {oc.id} suggested_resolve: vague guest response")
                    break
        
        # 다중 OC + 모호한 해소 → 자동 처리 안 함
        elif len(remaining_ocs) > 1:
            logger.debug(f"Multiple OCs ({len(remaining_ocs)}), skipping vague resolve")
        
        self._db.commit()
        return results
    
    def _matches_topic_context(self, text: str, topic: str, pattern: str) -> bool:
        """Topic 맥락에서 패턴 매칭"""
        import re
        
        # Topic별 키워드
        topic_keywords = {
            OCTopic.early_checkin.value: ['얼리', '체크인', '입실', '일찍'],
            OCTopic.follow_up.value: ['연락', '안내', '확인'],
            OCTopic.facility_issue.value: ['수리', '고장', '시설', '문제'],
            OCTopic.refund_check.value: ['환불', '취소', '반환'],
            OCTopic.payment.value: ['결제', '입금', '송금'],
            OCTopic.compensation.value: ['보상', '할인', '쿠폰'],
        }
        
        keywords = topic_keywords.get(topic, [])
        
        # 패턴 매칭
        if not re.search(pattern, text):
            return False
        
        # Topic 키워드 근처에서 패턴 발견
        for keyword in keywords:
            if keyword in text:
                return True
        
        return False
    
    # ─────────────────────────────────────────────────────────
    # OC 해소 (Host 메시지 기반)
    # ─────────────────────────────────────────────────────────
    
    async def process_host_followup(
        self,
        host_text: str,
        conversation_id: UUID,
    ) -> List[Tuple[OperationalCommitment, str]]:
        """
        Host 후속 메시지 기반 OC 처리
        
        규칙:
        - 자동 done ❌
        - 결과 안내로 보이면 → suggested_resolve
        """
        if not host_text:
            return []
        
        active_ocs = self._repo.get_active_by_conversation(conversation_id)
        if not active_ocs:
            return []
        
        results = []
        
        # 결과 안내 패턴
        result_patterns = [
            r'확인.*결과',
            r'안내.*드립니다',
            r'처리.*완료',
            r'해결.*되었',
            r'조치.*했습니다',
        ]
        
        import re
        for pattern in result_patterns:
            if re.search(pattern, host_text):
                # 관련 OC에 suggested_resolve
                for oc in active_ocs:
                    if oc.status == OCStatus.pending.value:
                        # Topic 연관성 체크 (간단히)
                        if oc.topic == OCTopic.follow_up.value:
                            oc.suggest_resolve(reason=OCResolutionReason.host_confirmed)
                            results.append((oc, "suggested_resolve"))
                            logger.info(f"OC {oc.id} suggested_resolve: host followup")
                break
        
        self._db.commit()
        return results
    
    # ─────────────────────────────────────────────────────────
    # Staff Notification
    # ─────────────────────────────────────────────────────────
    
    def get_staff_notifications(
        self,
        today: Optional[date] = None,
        limit: int = 50,
    ) -> List[StaffNotificationItem]:
        """
        Staff Notification Action Queue 조회
        
        노출 규칙:
        1. status = pending or suggested_resolve
        2. explicit: D-1부터 노출
        3. implicit: 즉시 노출
        """
        if today is None:
            today = date.today()
        
        # OC 조회
        ocs = self._repo.get_for_notification(today=today, limit=limit)
        
        # StaffNotificationItem으로 변환
        items = []
        
        for oc in ocs:
            # Conversation 조회 (guest 정보용)
            from sqlalchemy import select
            from app.domain.models.conversation import Conversation
            from app.domain.models.incoming_message import IncomingMessage, MessageDirection
            
            conv = self._db.execute(
                select(Conversation).where(Conversation.id == oc.conversation_id)
            ).scalar_one_or_none()
            
            if not conv:
                continue
            
            # 게스트 정보 조회
            guest_msg = self._db.execute(
                select(IncomingMessage)
                .where(
                    IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id,
                    IncomingMessage.direction == MessageDirection.incoming,
                    IncomingMessage.guest_name.isnot(None),
                )
                .order_by(IncomingMessage.received_at.asc())
                .limit(1)
            ).scalar_one_or_none()
            
            # Priority 계산
            guest_checkin = guest_msg.checkin_date if guest_msg else None
            priority = oc.calculate_priority(today, guest_checkin)
            
            items.append(StaffNotificationItem(
                oc_id=oc.id,
                conversation_id=oc.conversation_id,
                airbnb_thread_id=conv.airbnb_thread_id,
                topic=oc.topic,
                description=oc.description,
                evidence_quote=oc.evidence_quote,
                priority=priority,
                guest_name=guest_msg.guest_name if guest_msg else None,
                checkin_date=guest_msg.checkin_date if guest_msg else None,
                checkout_date=guest_msg.checkout_date if guest_msg else None,
                property_code=conv.property_code,
                property_name=guest_msg.ota_listing_name if guest_msg else None,
                status=oc.status,
                resolution_reason=oc.resolution_reason,
                resolution_evidence=oc.resolution_evidence,
                is_candidate_only=oc.is_candidate_only,
                target_time_type=oc.target_time_type,
                target_date=oc.target_date,
                created_at=oc.created_at,
            ))
        
        # Priority 순 정렬
        priority_order = {
            OCPriority.immediate: 0,
            OCPriority.upcoming: 1,
            OCPriority.pending: 2,
        }
        
        items.sort(key=lambda x: (
            priority_order.get(x.priority, 99),
            x.target_date or date.max,
            x.created_at or datetime.max,
        ))
        
        return items
    
    def get_conversation_ocs(
        self,
        conversation_id: UUID,
        include_resolved: bool = False,
    ) -> List[OperationalCommitment]:
        """
        Conversation의 OC 목록 조회 (Backlog용)
        """
        if include_resolved:
            return self._repo.get_by_conversation(conversation_id)
        else:
            return self._repo.get_active_by_conversation(conversation_id)
    
    # ─────────────────────────────────────────────────────────
    # 수동 액션
    # ─────────────────────────────────────────────────────────
    
    def mark_done(self, oc_id: UUID, by: str = "host") -> Optional[OperationalCommitment]:
        """OC 완료 처리"""
        oc = self._repo.mark_done(oc_id, by=by)
        if oc:
            self._db.commit()
            logger.info(f"OC {oc_id} marked done by {by}")
        return oc
    
    def confirm_resolve(self, oc_id: UUID, by: str = "host") -> Optional[OperationalCommitment]:
        """suggested_resolve 확정"""
        oc = self._repo.confirm_suggested_resolve(oc_id, by=by)
        if oc:
            self._db.commit()
            logger.info(f"OC {oc_id} resolve confirmed by {by}")
        return oc
    
    def reject_resolve(self, oc_id: UUID) -> Optional[OperationalCommitment]:
        """suggested_resolve 거부 → pending으로 복귀"""
        oc = self._repo.get_by_id(oc_id)
        if oc and oc.status == OCStatus.suggested_resolve.value:
            oc.status = OCStatus.pending.value
            oc.resolution_reason = None
            oc.updated_at = datetime.utcnow()
            self._db.commit()
            logger.info(f"OC {oc_id} resolve rejected, back to pending")
        return oc
    
    def confirm_candidate(self, oc_id: UUID) -> Optional[OperationalCommitment]:
        """후보 확정"""
        oc = self._repo.confirm_candidate(oc_id)
        if oc:
            self._db.commit()
            logger.info(f"OC candidate {oc_id} confirmed")
        return oc
    
    def reject_candidate(self, oc_id: UUID) -> Optional[OperationalCommitment]:
        """후보 거부"""
        oc = self._repo.reject_candidate(oc_id)
        if oc:
            self._db.commit()
            logger.info(f"OC candidate {oc_id} rejected")
        return oc
