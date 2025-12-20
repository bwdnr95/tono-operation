"""
CommitmentExtractor: LLM Layer - 발송 메시지에서 Commitment 후보 추출

핵심 원칙:
- LLM은 "후보"만 제시한다
- "확정"은 CommitmentService(TONO Layer)가 한다
- 추출 실패해도 시스템은 동작해야 한다 (graceful degradation)

이 모듈은 LLM의 "감각기관" 역할을 한다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.domain.models.commitment import CommitmentTopic, CommitmentType

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Commitment 후보 데이터 구조
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommitmentCandidate:
    """
    LLM이 추출한 Commitment 후보
    
    이 구조체는 "확정되지 않은 후보"임을 명확히 한다.
    CommitmentService가 검증 후 Commitment로 변환한다.
    """
    topic: str                    # CommitmentTopic 값
    type: str                     # CommitmentType 값
    value: dict                   # 구조화된 값
    provenance_text: str          # 근거 문장
    confidence: float             # 추출 신뢰도 (0~1)


class LLMExtractionResponse(BaseModel):
    """LLM 응답 파싱용 Pydantic 모델"""
    commitments: List[dict]


# ─────────────────────────────────────────────────────────────
# Commitment Extractor
# ─────────────────────────────────────────────────────────────

class CommitmentExtractor:
    """
    발송된 답변에서 Commitment 후보를 추출하는 LLM 레이어
    
    사용 시점: Sent 이벤트 발생 후
    호출자: CommitmentService.process_sent_message()
    
    LLM이 하는 일:
    - 답변 텍스트에서 약속/허용/금지 문장 감지
    - topic, type, value, provenance_text 구조화
    
    LLM이 하지 않는 일:
    - Commitment 확정 (CommitmentService가 함)
    - Conflict 판정 (ConflictDetector가 함)
    """
    
    # 지원하는 토픽 목록 (프롬프트에 포함)
    ALLOWED_TOPICS = [t.value for t in CommitmentTopic]
    ALLOWED_TYPES = [t.value for t in CommitmentType]
    
    def __init__(self) -> None:
        self._api_key = settings.LLM_API_KEY
        self._model = settings.LLM_MODEL or "gpt-4.1-mini"
    
    async def extract(
        self,
        sent_text: str,
        conversation_context: Optional[str] = None,
    ) -> List[CommitmentCandidate]:
        """
        발송된 답변에서 Commitment 후보 추출
        
        Args:
            sent_text: 발송된 답변 원문
            conversation_context: 대화 맥락 (있으면 정확도 향상)
        
        Returns:
            CommitmentCandidate 리스트 (빈 리스트 가능)
        """
        if not self._api_key:
            logger.warning("COMMITMENT_EXTRACTOR: LLM API key not set, skipping extraction")
            return []
        
        if not sent_text or not sent_text.strip():
            return []
        
        try:
            raw_response = await self._call_llm(sent_text, conversation_context)
            candidates = self._parse_response(raw_response)
            return candidates
        except Exception as e:
            logger.warning(f"COMMITMENT_EXTRACTOR: Extraction failed: {e}")
            return []
    
    async def _call_llm(
        self,
        sent_text: str,
        conversation_context: Optional[str],
    ) -> str:
        """LLM API 호출"""
        from openai import OpenAI
        
        client = OpenAI(api_key=self._api_key)
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(sent_text, conversation_context)
        
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # 낮은 temperature로 일관된 추출
        )
        
        return response.choices[0].message.content or ""
    
    def _build_system_prompt(self) -> str:
        """시스템 프롬프트 생성"""
        return f"""당신은 숙박 운영 AI의 '약속 추출기'입니다.

호스트가 게스트에게 보낸 답변에서 "약속/허용/금지/요금/조건" 내용을 추출합니다.

## 추출 대상
게스트와의 약속이 될 수 있는 내용만 추출합니다:
- 허용: "가능합니다", "해드릴게요", "괜찮습니다"
- 금지: "불가합니다", "어렵습니다", "안됩니다"
- 요금: "추가 요금", "무료", "~원"
- 변경: "변경해드렸습니다", "조정했습니다"
- 조건부: "~하시면 가능합니다", "~경우에만"

## 추출하지 않는 것
- 단순 정보 안내 (체크인 시간 안내 등, 약속이 아닌 것)
- 인사말, 감사 표현
- 질문

## 출력 형식 (JSON만 출력)
```json
{{
  "commitments": [
    {{
      "topic": "early_checkin | late_checkout | checkin_time | checkout_time | guest_count_change | free_provision | extra_fee | reservation_change | pet_policy | special_request | other",
      "type": "allowance | prohibition | fee | change | condition",
      "value": {{"allowed": true/false, "time": "HH:MM", "amount": 0, "description": "..."}},
      "provenance_text": "추출 근거가 된 원문 문장",
      "confidence": 0.0 ~ 1.0
    }}
  ]
}}
```

## 주의사항
- 약속이 없으면 빈 배열 반환: {{"commitments": []}}
- provenance_text는 반드시 원문에서 그대로 복사
- confidence는 명확한 약속일수록 높게 (0.9+), 애매하면 낮게 (0.5 이하)
- 하나의 문장에 여러 약속이 있으면 각각 분리

## 허용된 topic 값
{self.ALLOWED_TOPICS}

## 허용된 type 값
{self.ALLOWED_TYPES}
"""

    def _build_user_prompt(
        self,
        sent_text: str,
        conversation_context: Optional[str],
    ) -> str:
        """사용자 프롬프트 생성"""
        parts = []
        
        if conversation_context:
            parts.append(f"[대화 맥락]\n{conversation_context}\n")
        
        parts.append(f"[호스트가 보낸 답변]\n{sent_text}\n")
        parts.append("\n위 답변에서 게스트와의 약속/허용/금지/요금/조건 내용을 추출해주세요.")
        parts.append("JSON 형식으로만 응답하세요.")
        
        return "\n".join(parts)
    
    def _parse_response(self, raw_response: str) -> List[CommitmentCandidate]:
        """LLM 응답 파싱"""
        if not raw_response:
            return []
        
        # JSON 블록 추출
        text = raw_response.strip()
        
        # ```json ... ``` 형태 처리
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        
        # JSON 배열/객체 시작점 찾기
        json_start = -1
        for i, char in enumerate(text):
            if char in '{[':
                json_start = i
                break
        
        if json_start == -1:
            logger.warning("COMMITMENT_EXTRACTOR: No JSON found in response")
            return []
        
        json_text = text[json_start:]
        
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"COMMITMENT_EXTRACTOR: JSON parse error: {e}")
            return []
        
        # commitments 배열 추출
        commitments_raw = data.get("commitments", [])
        if not isinstance(commitments_raw, list):
            return []
        
        candidates = []
        for item in commitments_raw:
            try:
                candidate = self._validate_and_convert(item)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                logger.warning(f"COMMITMENT_EXTRACTOR: Invalid commitment item: {e}")
                continue
        
        return candidates
    
    def _validate_and_convert(self, item: dict) -> Optional[CommitmentCandidate]:
        """개별 항목 검증 및 변환"""
        topic = item.get("topic", "").lower()
        type_ = item.get("type", "").lower()
        value = item.get("value", {})
        provenance_text = item.get("provenance_text", "")
        confidence = item.get("confidence", 0.5)
        
        # 필수 필드 검증
        if not topic or not type_ or not provenance_text:
            return None
        
        # topic 유효성 검증
        if topic not in self.ALLOWED_TOPICS:
            topic = CommitmentTopic.OTHER.value
        
        # type 유효성 검증
        if type_ not in self.ALLOWED_TYPES:
            return None  # type이 잘못되면 무시
        
        # confidence 범위 보정
        confidence = max(0.0, min(1.0, float(confidence)))
        
        # value가 dict가 아니면 변환
        if not isinstance(value, dict):
            value = {"raw": str(value)}
        
        return CommitmentCandidate(
            topic=topic,
            type=type_,
            value=value,
            provenance_text=provenance_text,
            confidence=confidence,
        )


# ─────────────────────────────────────────────────────────────
# 규칙 기반 Fallback Extractor
# ─────────────────────────────────────────────────────────────

class RuleBasedCommitmentExtractor:
    """
    LLM 실패 시 사용하는 규칙 기반 추출기
    
    단순 키워드 매칭으로 기본적인 Commitment 후보 추출
    정확도는 낮지만, LLM 없이도 동작 가능
    """
    
    # 토픽별 키워드
    TOPIC_KEYWORDS = {
        CommitmentTopic.EARLY_CHECKIN.value: [
            "얼리 체크인", "얼리체크인", "일찍 입실", "일찍 들어오",
        ],
        CommitmentTopic.LATE_CHECKOUT.value: [
            "레이트 체크아웃", "레이트체크아웃", "늦게 퇴실", "늦게 나가",
        ],
        CommitmentTopic.EXTRA_FEE.value: [
            "추가 요금", "추가요금", "별도 비용", "추가 비용",
        ],
        CommitmentTopic.FREE_PROVISION.value: [
            "무료로", "서비스로", "무상으로",
        ],
        CommitmentTopic.PET_POLICY.value: [
            "반려동물", "강아지", "고양이", "펫",
        ],
    }
    
    # 타입별 키워드
    TYPE_KEYWORDS = {
        CommitmentType.ALLOWANCE.value: [
            "가능합니다", "해드릴게요", "괜찮습니다", "허용",
            "가능해요", "드릴게요", "됩니다",
        ],
        CommitmentType.PROHIBITION.value: [
            "불가합니다", "어렵습니다", "안됩니다", "금지",
            "불가해요", "어려워요", "안돼요",
        ],
        CommitmentType.FEE.value: [
            "원", "만원", "비용", "요금",
        ],
        CommitmentType.CONDITION.value: [
            "경우에", "때만", "조건으로", "하시면",
        ],
    }
    
    def extract(self, sent_text: str) -> List[CommitmentCandidate]:
        """규칙 기반 추출"""
        if not sent_text:
            return []
        
        candidates = []
        sentences = self._split_sentences(sent_text)
        
        for sentence in sentences:
            topic = self._detect_topic(sentence)
            type_ = self._detect_type(sentence)
            
            if topic and type_:
                candidates.append(CommitmentCandidate(
                    topic=topic,
                    type=type_,
                    value={},
                    provenance_text=sentence.strip(),
                    confidence=0.5,  # 규칙 기반은 낮은 신뢰도
                ))
        
        return candidates
    
    def _split_sentences(self, text: str) -> List[str]:
        """문장 분리"""
        import re
        # 마침표, 느낌표, 물음표로 분리
        sentences = re.split(r'[.!?]\s*', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _detect_topic(self, sentence: str) -> Optional[str]:
        """토픽 감지"""
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            if any(kw in sentence for kw in keywords):
                return topic
        return None
    
    def _detect_type(self, sentence: str) -> Optional[str]:
        """타입 감지"""
        for type_, keywords in self.TYPE_KEYWORDS.items():
            if any(kw in sentence for kw in keywords):
                return type_
        return None
