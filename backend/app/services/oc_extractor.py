"""
Operational Commitment Extractor

LLM을 사용하여 Sent 메시지에서 OC 후보를 추출한다.

설계 원칙:
- LLM은 후보 추출자일 뿐, 결정자가 아님
- 모든 후보에는 topic, description, evidence_quote, confidence 포함
- 자동 생성 제한 topic은 candidate_only로 표시
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from app.domain.models.operational_commitment import (
    OCCandidate,
    OCTopic,
    OCTargetTimeType,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# LLM 기반 Extractor
# ─────────────────────────────────────────────────────────────

class OCExtractor:
    """
    LLM 기반 OC 후보 추출기
    
    역할:
    - Sent 메시지에서 운영 약속 후보 추출
    - topic, description, evidence_quote 생성
    - target_time_type 판단
    
    제한:
    - 확정하지 않음 (후보만 제시)
    - refund/payment/compensation은 candidate_only로 표시
    """
    
    SYSTEM_PROMPT = """당신은 숙박업 호스트 메시지에서 '운영 약속'을 추출하는 분석기입니다.

## 추출 대상 (Operational Commitment)
호스트가 게스트에게 한 약속 중, **이행하지 않으면 CS 사고로 이어질 수 있는 것**만 추출합니다.

## Topic 종류
- early_checkin: 얼리체크인 관련 약속
- follow_up: "확인 후 안내드리겠습니다" 등 후속 연락 약속
- facility_issue: 시설 문제 해결 약속
- refund_check: 환불 관련 약속 (민감)
- payment: 결제 관련 약속 (민감)
- compensation: 보상 관련 약속 (민감)

## target_time_type
- explicit: 명확한 시점이 있음 (예: "체크인 당일", "내일까지", "3시에")
- implicit: 시점이 불명확함 (예: "확인 후", "조치 후")

## 출력 형식
JSON 배열로 반환합니다. 약속이 없으면 빈 배열 []을 반환합니다.

```json
[
  {
    "topic": "early_checkin",
    "description": "14시 얼리체크인 허용",
    "evidence_quote": "14시에 입실 가능합니다",
    "target_time_type": "explicit",
    "target_date": "2024-12-20",
    "confidence": 0.95
  }
]
```

## 규칙
1. evidence_quote는 원문에서 그대로 인용 (최대 100자)
2. description은 간결하게 요약 (20자 내외)
3. target_date는 explicit일 때만, YYYY-MM-DD 형식
4. confidence는 0.0~1.0 사이 (0.7 이상만 유효)
5. 일반적인 인사/감사/안내는 추출 대상 아님
6. 불확실하면 추출하지 않음"""

    def __init__(self, llm_client=None):
        self._llm_client = llm_client
    
    async def extract_candidates(
        self,
        sent_text: str,
        guest_checkin_date: Optional[date] = None,
        context: Optional[str] = None,
    ) -> List[OCCandidate]:
        """
        Sent 메시지에서 OC 후보 추출
        
        Args:
            sent_text: 발송된 메시지 본문
            guest_checkin_date: 게스트 체크인 날짜 (target_date 계산용)
            context: 추가 컨텍스트 (이전 대화 요약 등)
        
        Returns:
            OC 후보 리스트
        """
        if not sent_text or len(sent_text.strip()) < 10:
            return []
        
        try:
            if self._llm_client:
                return await self._extract_with_llm(sent_text, guest_checkin_date, context)
            else:
                # LLM 없으면 규칙 기반 fallback
                return self._extract_rule_based(sent_text, guest_checkin_date)
        except Exception as e:
            logger.error(f"OC extraction failed: {e}")
            return self._extract_rule_based(sent_text, guest_checkin_date)
    
    async def _extract_with_llm(
        self,
        sent_text: str,
        guest_checkin_date: Optional[date],
        context: Optional[str],
    ) -> List[OCCandidate]:
        """LLM으로 추출"""
        user_content = f"""다음 호스트 메시지에서 운영 약속을 추출하세요.

[호스트 메시지]
{sent_text}
"""
        if guest_checkin_date:
            user_content += f"\n[게스트 체크인 날짜]: {guest_checkin_date.isoformat()}"
        
        if context:
            user_content += f"\n[대화 맥락]\n{context}"
        
        response = await self._llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        
        return self._parse_llm_response(response, guest_checkin_date)
    
    def _parse_llm_response(
        self,
        response: str,
        guest_checkin_date: Optional[date],
    ) -> List[OCCandidate]:
        """LLM 응답 파싱"""
        try:
            # JSON 추출
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if not json_match:
                return []
            
            items = json.loads(json_match.group())
            candidates = []
            
            for item in items:
                # confidence 필터
                confidence = float(item.get("confidence", 0))
                if confidence < 0.7:
                    continue
                
                # topic 유효성 검사
                topic = item.get("topic", "")
                valid_topics = {t.value for t in OCTopic}
                if topic not in valid_topics:
                    continue
                
                # target_date 파싱
                target_date = None
                if item.get("target_date"):
                    try:
                        target_date = date.fromisoformat(item["target_date"])
                    except ValueError:
                        pass
                
                # target_time_type 기본값
                target_time_type = item.get("target_time_type", OCTargetTimeType.implicit.value)
                if target_time_type == OCTargetTimeType.explicit.value and not target_date:
                    # explicit인데 날짜 없으면 implicit으로
                    target_time_type = OCTargetTimeType.implicit.value
                
                candidates.append(OCCandidate(
                    topic=topic,
                    description=item.get("description", "")[:100],
                    evidence_quote=item.get("evidence_quote", "")[:200],
                    confidence=confidence,
                    target_time_type=target_time_type,
                    target_date=target_date,
                ))
            
            return candidates
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return []
    
    def _extract_rule_based(
        self,
        sent_text: str,
        guest_checkin_date: Optional[date],
    ) -> List[OCCandidate]:
        """
        규칙 기반 OC 추출 (Fallback)
        
        LLM 실패 시 또는 테스트용
        """
        candidates = []
        text_lower = sent_text.lower()
        
        # 얼리체크인 패턴
        early_checkin_patterns = [
            (r'(\d{1,2})시.*입실.*가능', 'explicit'),
            (r'(\d{1,2})시.*체크인.*가능', 'explicit'),
            (r'얼리.*체크인.*가능', 'implicit'),
            (r'일찍.*입실.*가능', 'implicit'),
        ]
        
        for pattern, time_type in early_checkin_patterns:
            match = re.search(pattern, sent_text)
            if match:
                # 시간 추출 시도
                time_match = re.search(r'(\d{1,2})시', sent_text)
                target_date = guest_checkin_date if time_type == 'explicit' and guest_checkin_date else None
                
                candidates.append(OCCandidate(
                    topic=OCTopic.early_checkin.value,
                    description=f"얼리체크인 허용" + (f" ({time_match.group(1)}시)" if time_match else ""),
                    evidence_quote=match.group(0)[:100],
                    confidence=0.8,
                    target_time_type=time_type,
                    target_date=target_date,
                ))
                break
        
        # 후속 연락 패턴
        follow_up_patterns = [
            r'확인.*후.*안내',
            r'확인.*후.*연락',
            r'알아보고.*연락',
            r'체크.*후.*안내',
        ]
        
        for pattern in follow_up_patterns:
            match = re.search(pattern, sent_text)
            if match:
                candidates.append(OCCandidate(
                    topic=OCTopic.follow_up.value,
                    description="확인 후 안내 예정",
                    evidence_quote=match.group(0)[:100],
                    confidence=0.75,
                    target_time_type=OCTargetTimeType.implicit.value,
                    target_date=None,
                ))
                break
        
        # 시설 문제 패턴
        facility_patterns = [
            r'수리.*예정',
            r'고쳐.*드리겠',
            r'조치.*하겠',
            r'해결.*해.*드리겠',
        ]
        
        for pattern in facility_patterns:
            match = re.search(pattern, sent_text)
            if match:
                candidates.append(OCCandidate(
                    topic=OCTopic.facility_issue.value,
                    description="시설 문제 조치 예정",
                    evidence_quote=match.group(0)[:100],
                    confidence=0.75,
                    target_time_type=OCTargetTimeType.implicit.value,
                    target_date=None,
                ))
                break
        
        # 환불 패턴 (candidate_only)
        if re.search(r'환불.*해.*드리겠|환불.*진행', sent_text):
            candidates.append(OCCandidate(
                topic=OCTopic.refund_check.value,
                description="환불 처리 예정",
                evidence_quote=re.search(r'.{0,20}환불.{0,30}', sent_text).group(0) if re.search(r'.{0,20}환불.{0,30}', sent_text) else "환불",
                confidence=0.7,
                target_time_type=OCTargetTimeType.implicit.value,
                target_date=None,
            ))
        
        return candidates


# ─────────────────────────────────────────────────────────────
# 편의 함수
# ─────────────────────────────────────────────────────────────

def create_oc_extractor(llm_client=None) -> OCExtractor:
    """OCExtractor 인스턴스 생성"""
    return OCExtractor(llm_client=llm_client)
