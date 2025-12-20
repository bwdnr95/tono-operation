"""
ConflictDetector: TONO Layer - 규칙 기반 Commitment 충돌 감지

핵심 원칙:
- LLM이 아니라 "규칙"으로 판정한다
- 충돌 여부의 "최종 판단"은 이 모듈이 한다
- LLM은 후보 제시만, 여기서 확정한다

이 모듈은 TONO의 "두뇌" 중 판단 파트다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from enum import Enum

from app.domain.models.commitment import (
    Commitment,
    CommitmentTopic,
    CommitmentType,
    CommitmentStatus,
)
from app.services.commitment_extractor import CommitmentCandidate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Conflict 결과 데이터 구조
# ─────────────────────────────────────────────────────────────

class ConflictSeverity(str, Enum):
    """충돌 심각도"""
    LOW = "low"           # 경미한 차이 (톤 차이 등)
    MEDIUM = "medium"     # 주의 필요 (시간 차이 등)
    HIGH = "high"         # 심각한 충돌 (허용↔금지 반전)
    CRITICAL = "critical" # CS 사고 가능성 (금액 차이 등)


class ConflictType(str, Enum):
    """충돌 유형"""
    TYPE_REVERSAL = "type_reversal"       # 허용↔금지 반전
    VALUE_MISMATCH = "value_mismatch"     # 값 불일치 (시간, 금액 등)
    IMPLICIT_CONFLICT = "implicit_conflict"  # 암묵적 충돌
    AMBIGUOUS = "ambiguous"               # 모호한 표현


@dataclass(frozen=True)
class ConflictResult:
    """충돌 감지 결과"""
    has_conflict: bool
    conflict_type: Optional[ConflictType]
    severity: Optional[ConflictSeverity]
    message: str
    existing_commitment: Optional[Commitment]
    new_candidate: Optional[CommitmentCandidate]
    details: dict


# ─────────────────────────────────────────────────────────────
# Conflict Detector
# ─────────────────────────────────────────────────────────────

class ConflictDetector:
    """
    규칙 기반 Commitment 충돌 감지기
    
    이 클래스는 TONO Layer의 핵심 판단 모듈이다.
    LLM에 의존하지 않고, 명확한 규칙으로 충돌을 판정한다.
    
    사용 시점:
    1. 새 Commitment 저장 전 기존 Commitment와 비교
    2. Draft 생성 전 기존 Commitment와 충돌 검사
    """
    
    def detect_conflict(
        self,
        new_candidate: CommitmentCandidate,
        existing_commitments: List[Commitment],
    ) -> ConflictResult:
        """
        새 Commitment 후보와 기존 Commitment들 간의 충돌 감지
        
        Args:
            new_candidate: 새로 추출된 Commitment 후보
            existing_commitments: 기존 ACTIVE Commitment 목록
        
        Returns:
            ConflictResult: 충돌 여부 및 상세 정보
        """
        # 같은 topic의 기존 commitment 찾기
        existing = self._find_same_topic(new_candidate, existing_commitments)
        
        if not existing:
            # 같은 topic이 없으면 충돌 없음
            return ConflictResult(
                has_conflict=False,
                conflict_type=None,
                severity=None,
                message="",
                existing_commitment=None,
                new_candidate=new_candidate,
                details={},
            )
        
        # 충돌 유형별 검사
        return self._check_conflict(new_candidate, existing)
    
    def detect_conflicts_batch(
        self,
        candidates: List[CommitmentCandidate],
        existing_commitments: List[Commitment],
    ) -> List[ConflictResult]:
        """
        여러 후보에 대해 일괄 충돌 검사
        """
        results = []
        for candidate in candidates:
            result = self.detect_conflict(candidate, existing_commitments)
            results.append(result)
        return results
    
    def _find_same_topic(
        self,
        candidate: CommitmentCandidate,
        commitments: List[Commitment],
    ) -> Optional[Commitment]:
        """같은 topic의 기존 commitment 찾기"""
        for c in commitments:
            if c.topic == candidate.topic and c.status == CommitmentStatus.ACTIVE.value:
                return c
        return None
    
    def _check_conflict(
        self,
        new: CommitmentCandidate,
        existing: Commitment,
    ) -> ConflictResult:
        """두 Commitment 간 충돌 검사"""
        
        # 1. Type 반전 검사 (가장 심각)
        type_conflict = self._check_type_reversal(new, existing)
        if type_conflict:
            return type_conflict
        
        # 2. Value 불일치 검사
        value_conflict = self._check_value_mismatch(new, existing)
        if value_conflict:
            return value_conflict
        
        # 3. 암묵적 충돌 검사 (topic별 특수 규칙)
        implicit_conflict = self._check_implicit_conflict(new, existing)
        if implicit_conflict:
            return implicit_conflict
        
        # 충돌 없음 (또는 무시 가능한 수준)
        return ConflictResult(
            has_conflict=False,
            conflict_type=None,
            severity=None,
            message="",
            existing_commitment=existing,
            new_candidate=new,
            details={},
        )
    
    def _check_type_reversal(
        self,
        new: CommitmentCandidate,
        existing: Commitment,
    ) -> Optional[ConflictResult]:
        """
        Type 반전 검사: 허용↔금지 반전은 심각한 충돌
        """
        opposites = {
            (CommitmentType.ALLOWANCE.value, CommitmentType.PROHIBITION.value),
            (CommitmentType.PROHIBITION.value, CommitmentType.ALLOWANCE.value),
        }
        
        if (existing.type, new.type) in opposites:
            topic_label = self._get_topic_label(new.topic)
            
            return ConflictResult(
                has_conflict=True,
                conflict_type=ConflictType.TYPE_REVERSAL,
                severity=ConflictSeverity.HIGH,
                message=f"⚠️ [{topic_label}] 이전에 '{self._get_type_label(existing.type)}'했지만, "
                        f"지금은 '{self._get_type_label(new.type)}'하려고 합니다.\n"
                        f"이전 약속: \"{existing.provenance_text}\"",
                existing_commitment=existing,
                new_candidate=new,
                details={
                    "existing_type": existing.type,
                    "new_type": new.type,
                },
            )
        
        return None
    
    def _check_value_mismatch(
        self,
        new: CommitmentCandidate,
        existing: Commitment,
    ) -> Optional[ConflictResult]:
        """
        Value 불일치 검사: 시간, 금액 등의 불일치
        """
        topic = new.topic
        
        # 시간 관련 토픽
        if topic in [
            CommitmentTopic.EARLY_CHECKIN.value,
            CommitmentTopic.LATE_CHECKOUT.value,
            CommitmentTopic.CHECKIN_TIME.value,
            CommitmentTopic.CHECKOUT_TIME.value,
        ]:
            return self._check_time_mismatch(new, existing)
        
        # 금액 관련 토픽
        if topic == CommitmentTopic.EXTRA_FEE.value:
            return self._check_amount_mismatch(new, existing)
        
        # 인원 관련 토픽
        if topic == CommitmentTopic.GUEST_COUNT_CHANGE.value:
            return self._check_count_mismatch(new, existing)
        
        return None
    
    def _check_time_mismatch(
        self,
        new: CommitmentCandidate,
        existing: Commitment,
    ) -> Optional[ConflictResult]:
        """시간 불일치 검사"""
        new_time = new.value.get("time")
        existing_time = existing.value.get("time")
        
        if not new_time or not existing_time:
            return None
        
        # 시간 파싱 (HH:MM 형식)
        try:
            new_h, new_m = map(int, str(new_time).split(":"))
            exist_h, exist_m = map(int, str(existing_time).split(":"))
            
            new_minutes = new_h * 60 + new_m
            exist_minutes = exist_h * 60 + exist_m
            diff = abs(new_minutes - exist_minutes)
            
            # 30분 이상 차이나면 경고
            if diff >= 30:
                topic_label = self._get_topic_label(new.topic)
                
                severity = ConflictSeverity.MEDIUM
                if diff >= 60:  # 1시간 이상이면 HIGH
                    severity = ConflictSeverity.HIGH
                
                return ConflictResult(
                    has_conflict=True,
                    conflict_type=ConflictType.VALUE_MISMATCH,
                    severity=severity,
                    message=f"⚠️ [{topic_label}] 시간이 다릅니다.\n"
                            f"이전 약속: {existing_time}\n"
                            f"새 약속: {new_time}",
                    existing_commitment=existing,
                    new_candidate=new,
                    details={
                        "existing_time": existing_time,
                        "new_time": new_time,
                        "diff_minutes": diff,
                    },
                )
        except (ValueError, AttributeError):
            pass
        
        return None
    
    def _check_amount_mismatch(
        self,
        new: CommitmentCandidate,
        existing: Commitment,
    ) -> Optional[ConflictResult]:
        """금액 불일치 검사 (CS 사고 위험)"""
        new_amount = new.value.get("amount")
        existing_amount = existing.value.get("amount")
        
        if new_amount is None or existing_amount is None:
            return None
        
        try:
            new_amt = float(new_amount)
            exist_amt = float(existing_amount)
            
            if new_amt != exist_amt:
                diff = abs(new_amt - exist_amt)
                
                # 금액 충돌은 CRITICAL
                return ConflictResult(
                    has_conflict=True,
                    conflict_type=ConflictType.VALUE_MISMATCH,
                    severity=ConflictSeverity.CRITICAL,
                    message=f"🚨 [추가요금] 금액이 다릅니다!\n"
                            f"이전 고지: {int(exist_amt):,}원\n"
                            f"새 금액: {int(new_amt):,}원\n"
                            f"차이: {int(diff):,}원",
                    existing_commitment=existing,
                    new_candidate=new,
                    details={
                        "existing_amount": exist_amt,
                        "new_amount": new_amt,
                        "diff": diff,
                    },
                )
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _check_count_mismatch(
        self,
        new: CommitmentCandidate,
        existing: Commitment,
    ) -> Optional[ConflictResult]:
        """인원 불일치 검사"""
        new_count = new.value.get("count") or new.value.get("guest_count")
        existing_count = existing.value.get("count") or existing.value.get("guest_count")
        
        if new_count is None or existing_count is None:
            return None
        
        try:
            new_cnt = int(new_count)
            exist_cnt = int(existing_count)
            
            if new_cnt != exist_cnt:
                return ConflictResult(
                    has_conflict=True,
                    conflict_type=ConflictType.VALUE_MISMATCH,
                    severity=ConflictSeverity.HIGH,
                    message=f"⚠️ [인원변경] 인원 수가 다릅니다.\n"
                            f"이전 확인: {exist_cnt}명\n"
                            f"새 확인: {new_cnt}명",
                    existing_commitment=existing,
                    new_candidate=new,
                    details={
                        "existing_count": exist_cnt,
                        "new_count": new_cnt,
                    },
                )
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _check_implicit_conflict(
        self,
        new: CommitmentCandidate,
        existing: Commitment,
    ) -> Optional[ConflictResult]:
        """암묵적 충돌 검사 (topic별 특수 규칙)"""
        
        # 예: 무료 제공 → 추가 요금 (같은 대상에 대해)
        if (
            existing.topic == CommitmentTopic.FREE_PROVISION.value
            and new.topic == CommitmentTopic.EXTRA_FEE.value
        ):
            # description이 겹치는지 확인
            existing_desc = existing.value.get("description", "").lower()
            new_desc = new.value.get("description", "").lower()
            
            # 간단한 키워드 매칭
            if existing_desc and new_desc:
                common_words = set(existing_desc.split()) & set(new_desc.split())
                if common_words - {"를", "을", "에", "의", "이", "가"}:
                    return ConflictResult(
                        has_conflict=True,
                        conflict_type=ConflictType.IMPLICIT_CONFLICT,
                        severity=ConflictSeverity.HIGH,
                        message=f"⚠️ 이전에 무료 제공한다고 했는데, 추가 요금을 언급합니다.\n"
                                f"이전: \"{existing.provenance_text}\"",
                        existing_commitment=existing,
                        new_candidate=new,
                        details={
                            "common_keywords": list(common_words),
                        },
                    )
        
        return None
    
    # ─────────────────────────────────────────────────────────
    # 유틸리티 메서드
    # ─────────────────────────────────────────────────────────
    
    @staticmethod
    def _get_topic_label(topic: str) -> str:
        """토픽 한글 라벨"""
        labels = {
            "early_checkin": "얼리체크인",
            "late_checkout": "레이트체크아웃",
            "checkin_time": "체크인시간",
            "checkout_time": "체크아웃시간",
            "guest_count_change": "인원변경",
            "free_provision": "무료제공",
            "extra_fee": "추가요금",
            "reservation_change": "예약변경",
            "pet_policy": "반려동물",
            "special_request": "특별요청",
            "other": "기타",
        }
        return labels.get(topic, topic)
    
    @staticmethod
    def _get_type_label(type_: str) -> str:
        """타입 한글 라벨"""
        labels = {
            "allowance": "허용",
            "prohibition": "금지",
            "fee": "요금 안내",
            "change": "변경",
            "condition": "조건부 허용",
        }
        return labels.get(type_, type_)
