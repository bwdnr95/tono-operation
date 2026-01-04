# backend/app/services/orchestrator_core.py
"""
TONO Orchestrator Core

판단(Decision) 엔진: Draft에 대해 어떤 액션을 취할지 결정

v2 변경사항:
- 패턴 매칭 로직 수정 (실제 작동하도록)
- AUTO_SEND 조건 개선
- 기본값을 SUGGEST_SEND로 변경 (데이터 축적 단계)

핵심 원칙:
1. BLOCK만 실제로 발송을 막음
2. AUTO_SEND는 패턴 매칭 + is_auto_approved일 때만
3. SUGGEST_SEND/REQUIRE_REVIEW는 사람이 버튼 누르면 발송됨
4. Decision Log는 항상 기록 (학습 데이터)
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.orchestrator import (
    Decision, 
    ReasonCode, 
    HumanAction,
    DecisionLog, 
    AutomationPattern, 
    PolicyRule,
)


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Evidence Package: 판단에 필요한 모든 정보
# ═══════════════════════════════════════════════════════════════

@dataclass
class EvidencePackage:
    """Orchestrator가 판단하는 데 필요한 모든 증거"""
    
    # 필수
    draft_content: str
    guest_message: str
    
    # 컨텍스트
    conversation_id: Optional[uuid.UUID] = None
    airbnb_thread_id: Optional[str] = None
    property_code: Optional[str] = None
    draft_reply_id: Optional[uuid.UUID] = None
    draft_id: Optional[uuid.UUID] = None  # 별칭
    
    # Outcome Label (AutoReplyService에서 생성)
    outcome_label: Optional[Dict[str, Any]] = None
    
    # 기존 Commitments (충돌 검사용)
    active_commitments: List[Dict[str, Any]] = field(default_factory=list)
    
    # 추가 메타데이터
    guest_name: Optional[str] = None
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# Decision Result
# ═══════════════════════════════════════════════════════════════

@dataclass
class DecisionResult:
    """Orchestrator의 판단 결과"""
    
    decision: Decision
    reason_codes: List[ReasonCode]
    confidence: float
    
    # 경고 및 필수 필드
    warnings: List[str] = field(default_factory=list)
    required_fields: List[str] = field(default_factory=list)
    
    # 충돌 정보
    commitment_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    
    # 매칭된 패턴
    matched_pattern_id: Optional[uuid.UUID] = None
    matched_pattern_name: Optional[str] = None
    
    # Decision Log ID (추적용)
    decision_log_id: Optional[uuid.UUID] = None
    
    @property
    def requires_human(self) -> bool:
        """사람의 확인/액션이 필요한지"""
        return self.decision in [
            Decision.BLOCK,
            Decision.REQUIRE_REVIEW,
            Decision.REQUIRE_EDIT,
        ]
    
    @property
    def can_auto_send(self) -> bool:
        """자동 발송 가능 여부"""
        return self.decision == Decision.AUTO_SEND
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_codes": [rc.value for rc in self.reason_codes],
            "confidence": self.confidence,
            "warnings": self.warnings,
            "requires_human": self.requires_human,
            "can_auto_send": self.can_auto_send,
            "commitment_conflicts": self.commitment_conflicts,
            "matched_pattern": self.matched_pattern_name,
        }


# ═══════════════════════════════════════════════════════════════
# Orchestrator Service
# ═══════════════════════════════════════════════════════════════

class OrchestratorService:
    """
    TONO Orchestrator 핵심 서비스
    
    책임:
    1. Evidence 수집 및 분석
    2. Rule/Pattern 기반 판단
    3. Decision 산출 및 로깅
    4. Human Action 기록
    """
    
    def __init__(self, db: Session):
        self._db = db
    
    # ─────────────────────────────────────────────────────
    # Main Entry Point
    # ─────────────────────────────────────────────────────
    
    async def evaluate_draft(
        self,
        evidence: EvidencePackage,
    ) -> DecisionResult:
        """
        Draft에 대한 판단 수행
        
        1. Reason Codes 수집
        2. 패턴 매칭
        3. 충돌 검사
        4. 최종 Decision 산출
        5. 로그 기록
        """
        # 1. Reason Codes 수집
        reason_codes = await self._collect_reason_codes(evidence)
        
        # 2. 패턴 매칭
        pattern_match = self._match_automation_pattern(evidence, reason_codes)
        
        # 3. 충돌 검사
        conflicts = self._check_commitment_conflicts(evidence)
        has_conflicts = len(conflicts) > 0
        
        # 4. 신뢰도 계산
        confidence = self._calculate_confidence(evidence, reason_codes)
        
        # 5. 경고 수집
        warnings = self._collect_warnings(evidence, reason_codes, conflicts)
        
        # 6. 최종 Decision 산출
        decision = self._compute_final_decision(
            reason_codes=reason_codes,
            pattern_match=pattern_match,
            has_conflicts=has_conflicts,
            confidence=confidence,
        )
        
        # 7. 필수 필드 체크
        required_fields = self._check_required_fields(evidence, reason_codes)
        
        # 8. 결과 생성 및 로깅
        return await self._finalize_decision(
            evidence=evidence,
            decision=decision,
            reason_codes=reason_codes,
            confidence=confidence,
            warnings=warnings,
            required_fields=required_fields,
            commitment_conflicts=conflicts,
            pattern_match=pattern_match,
        )
    
    # ─────────────────────────────────────────────────────
    # Reason Codes 수집
    # ─────────────────────────────────────────────────────
    
    async def _collect_reason_codes(
        self,
        evidence: EvidencePackage,
    ) -> List[ReasonCode]:
        """다양한 소스에서 Reason Codes 수집"""
        codes = []
        
        # 1. OutcomeLabel 기반 분석
        if evidence.outcome_label:
            codes.extend(self._analyze_outcome_label(evidence.outcome_label))
        
        # 2. 키워드 기반 분석
        codes.extend(self._analyze_keywords(evidence))
        
        # 3. Policy Rule 기반 분석
        codes.extend(self._apply_policy_rules(evidence))
        
        # 중복 제거
        return list(set(codes))
    
    def _analyze_outcome_label(
        self,
        outcome_label: Dict[str, Any],
    ) -> List[ReasonCode]:
        """OutcomeLabel 분석"""
        codes = []
        
        # Safety Outcome 분석
        safety = outcome_label.get("safety_outcome", "")
        if safety == "HIGH_RISK":
            codes.append(ReasonCode.SAFETY_CONCERN)
        elif safety == "SENSITIVE":
            codes.append(ReasonCode.SENSITIVE_TOPIC)
        elif safety == "NORMAL":
            codes.append(ReasonCode.SAFE_CONTENT)
        
        # Response Outcome 분석
        response = outcome_label.get("response_outcome", "")
        if response == "ANSWERED_GROUNDED":
            codes.append(ReasonCode.FAQ_GROUNDED)
        elif response == "PROFILE_GROUNDED":
            codes.append(ReasonCode.PROFILE_GROUNDED)
        elif response == "NEEDS_HOST_INPUT":
            codes.append(ReasonCode.MISSING_INFORMATION)
        elif response == "CLOSING_MESSAGE":
            codes.append(ReasonCode.CLOSING_MESSAGE)
        
        # Confidence 분석
        confidence = outcome_label.get("confidence", 0)
        if confidence >= 0.85:
            codes.append(ReasonCode.HIGH_CONFIDENCE)
        elif confidence < 0.6:
            codes.append(ReasonCode.LOW_CONFIDENCE)
        
        # Commitment 분석
        if outcome_label.get("has_new_commitment"):
            codes.append(ReasonCode.NEW_COMMITMENT)
        
        # Topic 분석
        topics = outcome_label.get("topics", [])
        sensitive_topics = {"refund", "compensation", "complaint", "safety", "legal"}
        if any(t.lower() in sensitive_topics for t in topics):
            codes.append(ReasonCode.SENSITIVE_TOPIC)
        
        return codes
    
    def _analyze_keywords(
        self,
        evidence: EvidencePackage,
    ) -> List[ReasonCode]:
        """키워드 기반 분석"""
        codes = []
        content = (evidence.draft_content or "").lower()
        guest_msg = (evidence.guest_message or "").lower()
        
        # 위험 키워드
        high_risk_keywords = ["환불", "보상", "법적", "소송", "경찰", "신고"]
        if any(kw in content or kw in guest_msg for kw in high_risk_keywords):
            codes.append(ReasonCode.HIGH_RISK_KEYWORDS)
        
        # 금액 관련
        import re
        money_pattern = r'\d+[만천백]\s*원|\d{1,3}(,\d{3})*\s*원|₩\d+'
        if re.search(money_pattern, content):
            codes.append(ReasonCode.FINANCIAL_MENTION)
        
        # 불만/클레임 키워드
        complaint_keywords = ["불만", "실망", "화가", "짜증", "최악", "더럽"]
        if any(kw in guest_msg for kw in complaint_keywords):
            codes.append(ReasonCode.COMPLAINT_DETECTED)
        
        # 단순 문의 키워드
        simple_keywords = ["비밀번호", "와이파이", "체크인", "체크아웃", "주차", "위치"]
        if any(kw in guest_msg for kw in simple_keywords) and ReasonCode.HIGH_RISK_KEYWORDS not in codes:
            codes.append(ReasonCode.SIMPLE_INQUIRY)
        
        return codes
    
    def _apply_policy_rules(
        self,
        evidence: EvidencePackage,
    ) -> List[ReasonCode]:
        """Policy Rule 적용"""
        codes = []
        
        # 활성 룰 조회
        stmt = select(PolicyRule).where(PolicyRule.is_active == True)
        
        if evidence.property_code:
            stmt = stmt.where(
                (PolicyRule.property_code == evidence.property_code) |
                (PolicyRule.property_code.is_(None))
            )
        
        rules = self._db.execute(stmt).scalars().all()
        
        for rule in rules:
            if self._matches_rule(evidence, rule):
                try:
                    code = ReasonCode(rule.applies_reason_code)
                    codes.append(code)
                except ValueError:
                    pass
        
        return codes
    
    def _matches_rule(
        self,
        evidence: EvidencePackage,
        rule: PolicyRule,
    ) -> bool:
        """Rule 매칭"""
        conditions = rule.conditions or {}
        content = (evidence.draft_content or "").lower()
        guest_msg = (evidence.guest_message or "").lower()
        
        # 키워드 매칭
        if "keywords" in conditions:
            keywords = conditions["keywords"]
            if isinstance(keywords, list):
                if not any(kw.lower() in content or kw.lower() in guest_msg for kw in keywords):
                    return False
        
        # 토픽 매칭
        if "topics" in conditions and evidence.outcome_label:
            topics = evidence.outcome_label.get("topics", [])
            if not any(t in conditions["topics"] for t in topics):
                return False
        
        return True
    
    # ─────────────────────────────────────────────────────
    # 패턴 매칭 (AUTO_SEND 핵심)
    # ─────────────────────────────────────────────────────
    
    def _match_automation_pattern(
        self,
        evidence: EvidencePackage,
        reason_codes: List[ReasonCode],
    ) -> Optional[Dict[str, Any]]:
        """자동화 패턴 매칭"""
        # 활성 패턴 조회
        stmt = select(AutomationPattern).where(
            AutomationPattern.is_active == True
        )
        
        if evidence.property_code:
            stmt = stmt.where(
                (AutomationPattern.property_code == evidence.property_code) |
                (AutomationPattern.property_code.is_(None))
            )
        
        patterns = self._db.execute(stmt).scalars().all()
        
        for pattern in patterns:
            if self._matches_pattern(evidence, pattern, reason_codes):
                logger.info(f"Pattern matched: {pattern.name}")
                return {
                    "id": pattern.id,
                    "name": pattern.name,
                    "is_auto_approved": pattern.is_auto_approved,
                    "approval_rate": pattern.approval_rate,
                }
        
        return None
    
    def _matches_pattern(
        self,
        evidence: EvidencePackage,
        pattern: AutomationPattern,
        reason_codes: List[ReasonCode],
    ) -> bool:
        """
        패턴 매칭 로직
        
        Returns:
            bool: 패턴과 매칭되면 True
        """
        conditions = pattern.conditions or {}
        
        # ─────────────────────────────────────────────────────
        # 1. 위험 코드가 있으면 매칭 안 됨
        # ─────────────────────────────────────────────────────
        danger_codes = {
            ReasonCode.HIGH_RISK_KEYWORDS,
            ReasonCode.SAFETY_CONCERN,
            ReasonCode.COMPLAINT_DETECTED,
        }
        if any(code in danger_codes for code in reason_codes):
            return False
        
        # ─────────────────────────────────────────────────────
        # 2. safety_outcomes 체크
        # ─────────────────────────────────────────────────────
        if "safety_outcomes" in conditions and evidence.outcome_label:
            safety = evidence.outcome_label.get("safety_outcome", "")
            if safety not in conditions["safety_outcomes"]:
                return False
        
        # ─────────────────────────────────────────────────────
        # 3. response_outcomes 체크
        # ─────────────────────────────────────────────────────
        if "response_outcomes" in conditions and evidence.outcome_label:
            response = evidence.outcome_label.get("response_outcome", "")
            if response not in conditions["response_outcomes"]:
                return False
        
        # ─────────────────────────────────────────────────────
        # 4. message_type 체크
        # ─────────────────────────────────────────────────────
        if "message_type" in conditions:
            msg_type = conditions["message_type"]
            
            if msg_type == "simple_inquiry":
                # SIMPLE_INQUIRY 또는 FAQ_GROUNDED가 있어야 함
                if not any(code in [ReasonCode.SIMPLE_INQUIRY, ReasonCode.FAQ_GROUNDED] 
                          for code in reason_codes):
                    return False
                    
            elif msg_type == "closing":
                # CLOSING_MESSAGE가 있어야 함
                if ReasonCode.CLOSING_MESSAGE not in reason_codes:
                    return False
        
        # ─────────────────────────────────────────────────────
        # 5. excluded_topics 체크
        # ─────────────────────────────────────────────────────
        if "excluded_topics" in conditions and evidence.outcome_label:
            topics = evidence.outcome_label.get("topics", [])
            excluded = conditions["excluded_topics"]
            if any(t.lower() in [e.lower() for e in excluded] for t in topics):
                return False
        
        # ─────────────────────────────────────────────────────
        # 6. confidence_min 체크
        # ─────────────────────────────────────────────────────
        if "confidence_min" in conditions and evidence.outcome_label:
            confidence = evidence.outcome_label.get("confidence", 0)
            if confidence < conditions["confidence_min"]:
                return False
        
        # ─────────────────────────────────────────────────────
        # 7. max_commitment_count 체크
        # ─────────────────────────────────────────────────────
        if "max_commitment_count" in conditions:
            if len(evidence.active_commitments) > conditions["max_commitment_count"]:
                return False
        
        # 모든 조건 통과
        logger.info(f"Pattern {pattern.name} matched!")
        return True
    
    # ─────────────────────────────────────────────────────
    # 충돌 검사
    # ─────────────────────────────────────────────────────
    
    def _check_commitment_conflicts(
        self,
        evidence: EvidencePackage,
    ) -> List[Dict[str, Any]]:
        """Commitment 충돌 검사"""
        conflicts = []
        
        if not evidence.active_commitments:
            return conflicts
        
        draft_lower = (evidence.draft_content or "").lower()
        
        for commitment in evidence.active_commitments:
            topic = commitment.get("topic", "")
            ctype = commitment.get("type", "")
            provenance = commitment.get("provenance_text", "")
            
            # 간단한 충돌 검사 (동일 토픽에 대해 다른 내용)
            # TODO: 더 정교한 LLM 기반 충돌 검사
            
            # 체크인 시간 충돌 예시
            if topic == "checkin_time":
                if "체크인" in draft_lower and any(
                    time in draft_lower for time in ["14시", "15시", "16시"]
                ):
                    if provenance and any(
                        time in provenance for time in ["14시", "15시", "16시"]
                    ):
                        # 다른 시간이 언급되었는지 확인
                        pass  # 더 정교한 검사 필요
        
        return conflicts
    
    # ─────────────────────────────────────────────────────
    # 신뢰도 및 경고
    # ─────────────────────────────────────────────────────
    
    def _calculate_confidence(
        self,
        evidence: EvidencePackage,
        reason_codes: List[ReasonCode],
    ) -> float:
        """신뢰도 계산"""
        base = 0.5
        
        # Outcome Label 신뢰도
        if evidence.outcome_label:
            label_confidence = evidence.outcome_label.get("confidence", 0.5)
            base = (base + label_confidence) / 2
        
        # Positive codes
        positive_codes = {
            ReasonCode.FAQ_GROUNDED,
            ReasonCode.PROFILE_GROUNDED,
            ReasonCode.HIGH_CONFIDENCE,
            ReasonCode.SAFE_CONTENT,
            ReasonCode.SIMPLE_INQUIRY,
            ReasonCode.CLOSING_MESSAGE,
        }
        positive_count = sum(1 for c in reason_codes if c in positive_codes)
        base += positive_count * 0.1
        
        # Negative codes
        negative_codes = {
            ReasonCode.LOW_CONFIDENCE,
            ReasonCode.MISSING_INFORMATION,
            ReasonCode.SENSITIVE_TOPIC,
        }
        negative_count = sum(1 for c in reason_codes if c in negative_codes)
        base -= negative_count * 0.15
        
        return max(0.0, min(1.0, base))
    
    def _collect_warnings(
        self,
        evidence: EvidencePackage,
        reason_codes: List[ReasonCode],
        conflicts: List[Dict[str, Any]],
    ) -> List[str]:
        """경고 수집"""
        warnings = []
        
        if ReasonCode.NEW_COMMITMENT in reason_codes:
            warnings.append("새로운 약속이 포함되어 있습니다")
        
        if ReasonCode.FINANCIAL_MENTION in reason_codes:
            warnings.append("금액 언급이 포함되어 있습니다")
        
        if conflicts:
            warnings.append(f"기존 약속과 충돌 가능성: {len(conflicts)}건")
        
        if ReasonCode.LOW_CONFIDENCE in reason_codes:
            warnings.append("AI 신뢰도가 낮습니다")
        
        return warnings
    
    def _check_required_fields(
        self,
        evidence: EvidencePackage,
        reason_codes: List[ReasonCode],
    ) -> List[str]:
        """필수 필드 체크"""
        required = []
        
        if ReasonCode.MISSING_INFORMATION in reason_codes:
            # TODO: 구체적으로 어떤 정보가 필요한지 분석
            required.append("추가 정보 필요")
        
        return required
    
    # ─────────────────────────────────────────────────────
    # 최종 Decision 산출
    # ─────────────────────────────────────────────────────
    
    def _compute_final_decision(
        self,
        reason_codes: List[ReasonCode],
        pattern_match: Optional[Dict[str, Any]],
        has_conflicts: bool,
        confidence: float,
    ) -> Decision:
        """최종 Decision 산출"""
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. BLOCK: 절대적 차단 조건
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        block_codes = {
            ReasonCode.HIGH_RISK_KEYWORDS,
            ReasonCode.SAFETY_CONCERN,
            ReasonCode.POLICY_VIOLATION,
        }
        if any(code in block_codes for code in reason_codes):
            return Decision.BLOCK
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. AUTO_SEND: 패턴 매칭 + 자동 승인
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if pattern_match and pattern_match.get("is_auto_approved"):
            # 추가 안전 체크
            dangerous_for_auto = {
                ReasonCode.SENSITIVE_TOPIC,
                ReasonCode.COMPLAINT_DETECTED,
                ReasonCode.NEW_COMMITMENT,
                ReasonCode.FINANCIAL_MENTION,
            }
            if not any(code in dangerous_for_auto for code in reason_codes):
                if confidence >= 0.7:  # 최소 70% 신뢰도
                    return Decision.AUTO_SEND
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. REQUIRE_EDIT: 수정이 필요한 경우
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        edit_codes = {
            ReasonCode.PERSONAL_INFO,
            ReasonCode.FINANCIAL_MENTION,
        }
        if any(code in edit_codes for code in reason_codes):
            return Decision.REQUIRE_EDIT
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4. REQUIRE_REVIEW: 검토가 필요한 경우
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        review_codes = {
            ReasonCode.SENSITIVE_TOPIC,
            ReasonCode.LOW_CONFIDENCE,
            ReasonCode.MISSING_INFORMATION,
            ReasonCode.NEW_COMMITMENT,
            ReasonCode.COMPLAINT_DETECTED,
        }
        if any(code in review_codes for code in reason_codes):
            return Decision.REQUIRE_REVIEW
        
        # 충돌 있으면 REQUIRE_REVIEW
        if has_conflicts:
            return Decision.REQUIRE_REVIEW
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 5. 기본값: SUGGEST_SEND
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 특별히 문제 없으면 발송 권장 (사람이 버튼 누르면 발송됨)
        return Decision.SUGGEST_SEND
    
    # ─────────────────────────────────────────────────────
    # 결과 생성 및 로깅
    # ─────────────────────────────────────────────────────
    
    async def _finalize_decision(
        self,
        evidence: EvidencePackage,
        decision: Decision,
        reason_codes: List[ReasonCode],
        confidence: float,
        warnings: List[str],
        required_fields: List[str],
        commitment_conflicts: List[Dict[str, Any]],
        pattern_match: Optional[Dict[str, Any]],
    ) -> DecisionResult:
        """결과 생성 및 DB 로깅"""
        
        matched_pattern_id = pattern_match["id"] if pattern_match else None
        matched_pattern_name = pattern_match["name"] if pattern_match else None
        
        # Decision Log 생성
        log = DecisionLog(
            draft_id=evidence.draft_reply_id or evidence.draft_id,
            conversation_id=evidence.conversation_id,
            airbnb_thread_id=evidence.airbnb_thread_id or "",
            property_code=evidence.property_code,
            guest_message=evidence.guest_message or "",
            draft_content=evidence.draft_content or "",
            decision=decision.value,
            reason_codes=[rc.value for rc in reason_codes],
            decision_details={
                "warnings": warnings,
                "conflicts": commitment_conflicts,
            },
            confidence=confidence,
            pattern_id=matched_pattern_id,
        )
        
        self._db.add(log)
        self._db.flush()
        
        logger.info(
            f"Decision: {decision.value}, confidence={confidence:.2f}, "
            f"pattern={matched_pattern_name}, log_id={log.id}"
        )
        
        return DecisionResult(
            decision=decision,
            reason_codes=reason_codes,
            confidence=confidence,
            warnings=warnings,
            required_fields=required_fields,
            commitment_conflicts=commitment_conflicts,
            matched_pattern_id=matched_pattern_id,
            matched_pattern_name=matched_pattern_name,
            decision_log_id=log.id,
        )
    
    # ─────────────────────────────────────────────────────
    # Human Action 기록
    # ─────────────────────────────────────────────────────
    
    def record_human_action(
        self,
        decision_log_id: uuid.UUID,
        action: HumanAction,
        actor: str,
        edited_content: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Optional[DecisionLog]:
        """인간 액션 기록"""
        log = self._db.get(DecisionLog, decision_log_id)
        if not log:
            return None
        
        log.record_human_action(
            action=action,
            actor=actor,
            edited_content=edited_content,
            comment=comment,
        )
        
        # 패턴 통계 업데이트
        if log.pattern_id:
            pattern = self._db.get(AutomationPattern, log.pattern_id)
            if pattern:
                pattern.increment_match(action)
        
        self._db.flush()
        return log
    
    def record_sent(
        self,
        decision_log_id: uuid.UUID,
        final_content: str,
    ) -> Optional[DecisionLog]:
        """발송 완료 기록"""
        log = self._db.get(DecisionLog, decision_log_id)
        if not log:
            return None
        
        log.record_sent(final_content)
        self._db.flush()
        return log
    
    # ─────────────────────────────────────────────────────
    # 통계 조회 (Retrospective용)
    # ─────────────────────────────────────────────────────
    
    def get_decision_stats(
        self,
        property_code: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Decision 통계 조회"""
        from datetime import timedelta
        from sqlalchemy import func
        
        since = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(
            DecisionLog.decision,
            DecisionLog.human_action,
            func.count().label("count"),
        ).where(
            DecisionLog.created_at >= since
        ).group_by(
            DecisionLog.decision,
            DecisionLog.human_action,
        )
        
        if property_code:
            stmt = stmt.where(DecisionLog.property_code == property_code)
        
        results = self._db.execute(stmt).all()
        
        stats = {
            "total": 0,
            "by_decision": {},
            "by_human_action": {},
            "automation_candidates": 0,
        }
        
        for row in results:
            decision, human_action, count = row
            stats["total"] += count
            
            if decision not in stats["by_decision"]:
                stats["by_decision"][decision] = 0
            stats["by_decision"][decision] += count
            
            if human_action:
                if human_action not in stats["by_human_action"]:
                    stats["by_human_action"][human_action] = 0
                stats["by_human_action"][human_action] += count
                
                # 수정 없이 승인된 것 = 자동화 후보
                if human_action == HumanAction.APPROVED_AS_IS.value:
                    stats["automation_candidates"] += count
        
        return stats


# Alias for backward compatibility
OrchestratorCore = OrchestratorService
