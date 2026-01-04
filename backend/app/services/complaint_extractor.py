# backend/app/services/complaint_extractor.py
"""
Complaint 추출 서비스

게스트 메시지에서 불만/문제를 감지하여 Complaint를 생성한다.

설계 원칙:
- 게스트 메시지 수신 시점에 호출
- LLM으로 불만/문제 감지 및 분류
- 감지된 경우에만 Complaint 생성
- 중복 방지: 같은 conversation + 유사 내용은 생성 안 함
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.domain.models.complaint import (
    Complaint, 
    ComplaintCategory, 
    ComplaintSeverity, 
    ComplaintStatus,
)
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.conversation import Conversation
from app.adapters.llm_client import get_openai_client

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class ExtractedComplaint:
    """추출된 Complaint 정보"""
    category: str
    severity: str
    description: str
    evidence_quote: str
    confidence: float


@dataclass
class ComplaintExtractionResult:
    """추출 결과"""
    has_complaint: bool
    complaints: List[ExtractedComplaint]
    raw_response: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# Complaint Extractor Service
# ═══════════════════════════════════════════════════════════════

class ComplaintExtractor:
    """
    게스트 메시지에서 Complaint를 추출하는 서비스
    
    LLM 기반으로 모든 언어/표현 대응
    """
    
    def __init__(self, db: Session, openai_client=None):
        self._db = db
        self._openai_client = openai_client or get_openai_client()
    
    def extract_from_message(
        self,
        *,
        message: IncomingMessage,
        conversation: Conversation,
    ) -> ComplaintExtractionResult:
        """
        게스트 메시지에서 Complaint 추출
        
        Args:
            message: 게스트 메시지
            conversation: 대화
            
        Returns:
            ComplaintExtractionResult
        """
        guest_text = (message.pure_guest_message or "").strip()
        if not guest_text:
            return ComplaintExtractionResult(has_complaint=False, complaints=[])
        
        # LLM으로 분석 (Rule 기반 필터링 없음 - 모든 언어/표현 대응)
        result = self._extract_with_llm(guest_text)
        
        if not result.has_complaint:
            return result
        
        # 중복 체크 후 DB 저장
        created_complaints = []
        for extracted in result.complaints:
            # 중복 체크: 같은 conversation + 같은 category + open 상태
            existing = self._db.execute(
                select(Complaint).where(
                    and_(
                        Complaint.conversation_id == conversation.id,
                        Complaint.category == extracted.category,
                        Complaint.status.in_([
                            ComplaintStatus.open.value,
                            ComplaintStatus.in_progress.value,
                        ]),
                    )
                )
            ).scalar()
            
            if existing:
                logger.info(
                    f"COMPLAINT_EXTRACTOR: Duplicate complaint skipped - "
                    f"conversation_id={conversation.id}, category={extracted.category}"
                )
                continue
            
            # Complaint 생성
            complaint = Complaint(
                conversation_id=conversation.id,
                provenance_message_id=message.id,
                category=extracted.category,
                severity=extracted.severity,
                description=extracted.description,
                evidence_quote=extracted.evidence_quote,
                extraction_confidence=extracted.confidence,
                property_code=conversation.property_code or message.property_code or "",
                status=ComplaintStatus.open.value,
            )
            self._db.add(complaint)
            created_complaints.append(extracted)
            
            # 🔔 Notification 생성
            try:
                from app.services.notification_service import NotificationService
                from app.domain.models.complaint import COMPLAINT_CATEGORY_LABELS
                
                notification_svc = NotificationService(self._db)
                notification_svc.create_complaint_alert(
                    property_code=conversation.property_code or message.property_code or "",
                    guest_name=message.guest_name or "게스트",
                    category=extracted.category,
                    category_label=COMPLAINT_CATEGORY_LABELS.get(extracted.category, extracted.category),
                    severity=extracted.severity,
                    description=extracted.description,
                    airbnb_thread_id=conversation.airbnb_thread_id,
                    conversation_id=str(conversation.id),
                )
            except Exception as e:
                logger.warning(f"Failed to create complaint notification: {e}")
            
            logger.info(
                f"COMPLAINT_EXTRACTOR: Created complaint - "
                f"conversation_id={conversation.id}, "
                f"category={extracted.category}, "
                f"severity={extracted.severity}"
            )
        
        return ComplaintExtractionResult(
            has_complaint=len(created_complaints) > 0,
            complaints=created_complaints,
            raw_response=result.raw_response,
        )
    
    def _extract_with_llm(self, guest_text: str) -> ComplaintExtractionResult:
        """LLM으로 Complaint 추출"""
        system_prompt = self._build_system_prompt()
        user_prompt = f"""아래 게스트 메시지를 분석하세요:

---
{guest_text}
---

위 메시지에서 불만/문제가 있으면 JSON으로 추출하세요."""

        try:
            resp = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            
            raw_content = resp.choices[0].message.content or "{}"
            return self._parse_llm_response(raw_content)
            
        except Exception as exc:
            logger.warning(f"COMPLAINT_EXTRACTOR: LLM error - {exc}")
            return ComplaintExtractionResult(
                has_complaint=False, 
                complaints=[],
                raw_response=str(exc),
            )
    
    def _build_system_prompt(self) -> str:
        """Complaint 추출용 시스템 프롬프트"""
        categories = """
CATEGORY (하나 선택):
- hot_water: 온수 문제
- heating_cooling: 냉난방 문제
- wifi: 와이파이/인터넷 문제
- appliance: 가전제품 문제 (TV, 세탁기, 냉장고 등)
- plumbing: 배관/수도 문제
- electrical: 전기 문제
- door_lock: 도어락/잠금장치 문제
- facility: 기타 시설 문제
- cleanliness: 청소 불만
- bedding: 침구류 문제
- bathroom: 화장실 청결
- kitchen: 주방 청결
- noise: 소음
- smell: 냄새
- pest: 벌레/해충
- temperature: 실내 온도
- safety: 안전 문제
- security: 보안 문제
- description_mismatch: 설명과 다름
- amenity_missing: 어메니티 누락
- access: 출입/접근 문제
- other: 기타"""

        return f"""너는 숙박 게스트 메시지에서 불만/문제를 추출하는 분석가다.

게스트가 숙소의 문제점이나 불편함을 표현했는지 판단하고,
있다면 카테고리와 심각도를 분류한다.

{categories}

SEVERITY (심각도):
- low: 불편하지만 이용 가능 (사소한 문제)
- medium: 불편함, 조치 필요 (일반적인 문제)
- high: 심각한 불편, 즉시 조치 필요
- critical: 이용 불가, 긴급 대응 필요 (안전 문제 등)

판단 기준:
1. 단순 질문은 불만이 아님 (예: "와이파이 비번이 뭐에요?" → 불만 아님)
2. 문제 제기가 있어야 불만 (예: "와이파이가 안 돼요" → 불만)
3. 감사/칭찬은 불만이 아님
4. 하나의 메시지에 여러 불만이 있을 수 있음

OUTPUT FORMAT (JSON만 출력):
{{
  "has_complaint": true/false,
  "complaints": [
    {{
      "category": "카테고리",
      "severity": "심각도",
      "description": "문제 요약 (한 문장)",
      "evidence_quote": "게스트 원문 인용",
      "confidence": 0.0~1.0
    }}
  ]
}}

불만이 없으면:
{{
  "has_complaint": false,
  "complaints": []
}}"""

    def _parse_llm_response(self, raw_content: str) -> ComplaintExtractionResult:
        """LLM 응답 파싱"""
        try:
            # JSON 파싱
            parsed = json.loads(raw_content)
            
            has_complaint = parsed.get("has_complaint", False)
            if not has_complaint:
                return ComplaintExtractionResult(
                    has_complaint=False,
                    complaints=[],
                    raw_response=raw_content,
                )
            
            complaints = []
            for item in parsed.get("complaints", []):
                # 카테고리 검증
                category = item.get("category", "other")
                if category not in [c.value for c in ComplaintCategory]:
                    category = "other"
                
                # 심각도 검증
                severity = item.get("severity", "medium")
                if severity not in [s.value for s in ComplaintSeverity]:
                    severity = "medium"
                
                complaints.append(ExtractedComplaint(
                    category=category,
                    severity=severity,
                    description=item.get("description", ""),
                    evidence_quote=item.get("evidence_quote", ""),
                    confidence=float(item.get("confidence", 0.8)),
                ))
            
            return ComplaintExtractionResult(
                has_complaint=len(complaints) > 0,
                complaints=complaints,
                raw_response=raw_content,
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"COMPLAINT_EXTRACTOR: JSON parse error - {e}")
            return ComplaintExtractionResult(
                has_complaint=False,
                complaints=[],
                raw_response=raw_content,
            )


# ═══════════════════════════════════════════════════════════════
# 편의 함수
# ═══════════════════════════════════════════════════════════════

def extract_complaints_from_message(
    *,
    db: Session,
    message: IncomingMessage,
    conversation: Conversation,
) -> ComplaintExtractionResult:
    """
    게스트 메시지에서 Complaint 추출 (편의 함수)
    """
    extractor = ComplaintExtractor(db)
    return extractor.extract_from_message(
        message=message,
        conversation=conversation,
    )
