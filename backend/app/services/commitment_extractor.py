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
        return f"""당신은 숙박업 운영 시스템의 "약속 추출기"입니다.

## 당신의 역할
호스트가 게스트에게 보낸 답변에서 "약속(Commitment)"을 찾아 구조화합니다.

## 약속(Commitment)이란?
호스트가 게스트에게 한 **구속력 있는 언급**입니다.
핵심 판단 기준: "호스트가 이것을 지키지 않으면 게스트가 불만을 가질 수 있는가?"

### 약속의 유형
1. **허용/금지**: 게스트의 요청에 대한 가부 결정
2. **행동 약속**: 호스트가 하겠다고 한 행동
3. **요금/조건**: 금액이나 조건에 대한 확정
4. **변경 확정**: 예약 내용 변경 확정

## 판단 시 고려사항

### 대화 맥락이 중요합니다
- 게스트가 무엇을 물었는지 파악하세요
- "네 가능합니다"만 보면 모호하지만, 게스트 질문과 함께 보면 명확해집니다
- 맥락 없이는 판단이 어려우면 confidence를 낮추세요

### 약속으로 볼 수 있는 것 (예시)
- "얼리체크인 가능합니다" → 허용 약속
- "당일에 연락드리겠습니다" → 행동 약속
- "추가 요금 없이 해드릴게요" → 요금 확정
- "확인 후 다시 안내드리겠습니다" → 행동 약속
- "수건 추가로 준비해드릴게요" → 행동 약속
- "반려동물은 어렵습니다" → 금지

### 약속이 아닌 것 (예시)
- "체크인 시간은 15시입니다" → 고정된 숙소 정보 (변하지 않는 사실)
- "감사합니다" → 인사
- "궁금한 점 있으시면 말씀해주세요" → 일반적 안내
- "좋은 하루 되세요" → 인사

### 애매한 경우
- 확실하지 않으면 추출하되 confidence를 낮게 (0.4~0.6)
- 완전히 약속이 아닌 것만 제외하세요
- 과소추출보다 과다추출이 낫습니다 (시스템이 나중에 필터링)

## 출력 형식

JSON으로만 응답하세요:

```json
{{
  "commitments": [
    {{
      "topic": "토픽",
      "type": "유형",
      "value": {{"description": "구체적 내용", ...}},
      "provenance_text": "근거가 된 원문 문장 (정확히 복사)",
      "confidence": 0.0 ~ 1.0
    }}
  ]
}}
```

### topic 값 (가장 적합한 것 선택, 없으면 "other")
{self.ALLOWED_TOPICS}

### type 값
{self.ALLOWED_TYPES}

### value 필드 (해당하는 것만 포함)
- "allowed": true/false (허용/금지인 경우)
- "time": "HH:MM" (시간 관련인 경우)
- "amount": 숫자 (금액인 경우)
- "description": "구체적 설명" (항상 포함 권장)

### confidence 가이드
- 0.9+: 명확한 약속 ("네, 가능합니다", "해드리겠습니다")
- 0.7~0.9: 높은 확신 (문맥상 약속으로 보임)
- 0.5~0.7: 중간 확신 (약속일 수도 있음)
- 0.5 미만: 낮은 확신 (애매하지만 일단 추출)

## 주의사항
- 약속이 없으면 빈 배열: {{"commitments": []}}
- provenance_text는 원문에서 **정확히** 복사
- 하나의 문장에 여러 약속이 있으면 각각 분리
- 대화 맥락이 없으면 답변만으로 판단하되 confidence 낮춤"""

    def _build_user_prompt(
        self,
        sent_text: str,
        conversation_context: Optional[str],
    ) -> str:
        """사용자 프롬프트 생성"""
        parts = []
        
        if conversation_context:
            parts.append(f"## 대화 맥락\n{conversation_context}\n")
        else:
            parts.append("## 대화 맥락\n(제공되지 않음 - 답변만으로 판단하되 confidence를 낮춰주세요)\n")
        
        parts.append(f"## 호스트가 발송한 답변\n{sent_text}\n")
        parts.append("\n위 답변에서 게스트와의 약속(Commitment)을 추출해주세요.")
        
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
        
        # topic 유효성 검증 - 없으면 other로 (유연하게)
        if topic not in self.ALLOWED_TOPICS:
            topic = CommitmentTopic.OTHER.value
        
        # type 유효성 검증 - 없으면 other로 (유연하게, 기존은 무시했음)
        if type_ not in self.ALLOWED_TYPES:
            # 유사한 type 매핑 시도
            type_mapping = {
                "allow": "allowance",
                "permit": "allowance",
                "deny": "prohibition",
                "forbid": "prohibition",
                "price": "fee",
                "cost": "fee",
                "modify": "change",
                "update": "change",
            }
            type_ = type_mapping.get(type_, "allowance")  # 기본값 allowance
        
        # confidence 범위 보정
        confidence = max(0.0, min(1.0, float(confidence)))
        
        # value가 dict가 아니면 변환
        if not isinstance(value, dict):
            value = {"description": str(value)}
        
        return CommitmentCandidate(
            topic=topic,
            type=type_,
            value=value,
            provenance_text=provenance_text,
            confidence=confidence,
        )


# ─────────────────────────────────────────────────────────────
# 규칙 기반 Fallback Extractor (LLM 실패 시 사용)
# ─────────────────────────────────────────────────────────────

class RuleBasedCommitmentExtractor:
    """
    LLM 실패 시 사용하는 규칙 기반 추출기
    
    단순 키워드 매칭으로 기본적인 Commitment 후보 추출
    정확도는 낮지만, LLM 없이도 동작 가능
    """
    
    # 행동 약속 키워드 (새로 추가)
    ACTION_KEYWORDS = [
        "드리겠습니다", "하겠습니다", "해드릴게요", "해드리겠습니다",
        "연락드리", "안내드리", "확인해드리", "준비해드리",
        "보내드리", "전달드리",
    ]
    
    # 허용/금지 키워드
    ALLOWANCE_KEYWORDS = [
        "가능합니다", "가능해요", "됩니다", "괜찮습니다",
        "해드릴게요", "드릴게요", "허용",
    ]
    
    PROHIBITION_KEYWORDS = [
        "불가합니다", "불가해요", "어렵습니다", "어려워요",
        "안됩니다", "안돼요", "금지", "제한",
    ]
    
    # 토픽 감지 키워드
    TOPIC_KEYWORDS = {
        CommitmentTopic.EARLY_CHECKIN.value: [
            "얼리 체크인", "얼리체크인", "일찍 입실", "일찍 들어오",
            "빨리 입실", "먼저 들어오",
        ],
        CommitmentTopic.LATE_CHECKOUT.value: [
            "레이트 체크아웃", "레이트체크아웃", "늦게 퇴실", "늦게 나가",
            "늦은 퇴실",
        ],
        CommitmentTopic.EXTRA_FEE.value: [
            "추가 요금", "추가요금", "별도 비용", "추가 비용",
        ],
        CommitmentTopic.FREE_PROVISION.value: [
            "무료로", "서비스로", "무상으로", "추가 비용 없이",
        ],
        CommitmentTopic.PET_POLICY.value: [
            "반려동물", "강아지", "고양이", "펫", "애완",
        ],
        CommitmentTopic.GUEST_COUNT_CHANGE.value: [
            "인원", "명", "추가 인원", "성인", "아이",
        ],
        CommitmentTopic.SPECIAL_REQUEST.value: [
            "요청", "부탁", "준비", "수건", "베개", "이불",
        ],
    }
    
    def extract(self, sent_text: str) -> List[CommitmentCandidate]:
        """규칙 기반 추출"""
        if not sent_text:
            return []
        
        candidates = []
        sentences = self._split_sentences(sent_text)
        
        for sentence in sentences:
            # 행동 약속 먼저 체크
            if self._has_action_promise(sentence):
                topic = self._detect_topic(sentence) or CommitmentTopic.OTHER.value
                candidates.append(CommitmentCandidate(
                    topic=topic,
                    type=CommitmentType.ALLOWANCE.value,
                    value={"description": sentence.strip()},
                    provenance_text=sentence.strip(),
                    confidence=0.5,
                ))
                continue
            
            # 허용/금지 체크
            type_ = self._detect_type(sentence)
            if type_:
                topic = self._detect_topic(sentence) or CommitmentTopic.OTHER.value
                candidates.append(CommitmentCandidate(
                    topic=topic,
                    type=type_,
                    value={"description": sentence.strip()},
                    provenance_text=sentence.strip(),
                    confidence=0.5,
                ))
        
        return candidates
    
    def _split_sentences(self, text: str) -> List[str]:
        """문장 분리"""
        import re
        sentences = re.split(r'[.!?]\s*', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _has_action_promise(self, sentence: str) -> bool:
        """행동 약속 키워드 포함 여부"""
        return any(kw in sentence for kw in self.ACTION_KEYWORDS)
    
    def _detect_topic(self, sentence: str) -> Optional[str]:
        """토픽 감지"""
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            if any(kw in sentence for kw in keywords):
                return topic
        return None
    
    def _detect_type(self, sentence: str) -> Optional[str]:
        """타입 감지 (허용/금지)"""
        if any(kw in sentence for kw in self.PROHIBITION_KEYWORDS):
            return CommitmentType.PROHIBITION.value
        if any(kw in sentence for kw in self.ALLOWANCE_KEYWORDS):
            return CommitmentType.ALLOWANCE.value
        return None
