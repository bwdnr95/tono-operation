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
from datetime import date
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
    
    OC 생성 조건:
    - type이 "action_promise"인 경우
    - 또는 topic이 민감 토픽(refund, payment, compensation)인 경우
    """
    topic: str                    # CommitmentTopic 값
    type: str                     # CommitmentType 값
    value: dict                   # 구조화된 값
    provenance_text: str          # 근거 문장
    confidence: float             # 추출 신뢰도 (0~1)
    target_date: Optional[str] = None      # 🆕 이행 목표일 (YYYY-MM-DD)
    target_time_type: str = "implicit"     # 🆕 "explicit" | "implicit"


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
    
    def __init__(self, openai_client=None, model: str = None) -> None:
        """
        Args:
            openai_client: OpenAI 클라이언트 인스턴스 (DI)
            model: 사용할 모델 (기본값: settings.LLM_MODEL_PARSER)
        """
        self._client = openai_client
        # 단순 추출용 모델 (비용 절감)
        self._model = model or settings.LLM_MODEL_PARSER or "gpt-4o-mini"
    
    async def extract(
        self,
        sent_text: str,
        conversation_context: Optional[str] = None,
        guest_checkin_date: Optional[date] = None,
    ) -> List[CommitmentCandidate]:
        """
        발송된 답변에서 Commitment 후보 추출
        
        Args:
            sent_text: 발송된 답변 원문
            conversation_context: 대화 맥락 (있으면 정확도 향상)
            guest_checkin_date: 게스트 체크인 날짜 (날짜 파싱 정확도 향상)
        
        Returns:
            CommitmentCandidate 리스트 (빈 리스트 가능)
        """
        if not self._client:
            logger.warning("COMMITMENT_EXTRACTOR: LLM API key not set, skipping extraction")
            return []
        
        if not sent_text or not sent_text.strip():
            return []
        
        try:
            raw_response = await self._call_llm(sent_text, conversation_context, guest_checkin_date)
            candidates = self._parse_response(raw_response)
            return candidates
        except Exception as e:
            logger.warning(f"COMMITMENT_EXTRACTOR: Extraction failed: {e}")
            return []
    
    async def _call_llm(
        self,
        sent_text: str,
        conversation_context: Optional[str],
        guest_checkin_date: Optional[date] = None,
    ) -> str:
        """LLM API 호출"""
        if not self._client:
            logger.warning("COMMITMENT_EXTRACTOR: No OpenAI client available")
            return "[]"
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(sent_text, conversation_context, guest_checkin_date)
        
        response = self._client.chat.completions.create(
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

## type (유형) - 가장 중요!

### allowance (허용)
- "가능합니다", "괜찮습니다", "해드릴 수 있습니다"
- 게스트의 요청을 수락하는 경우

### prohibition (금지)
- "불가합니다", "어렵습니다", "안 됩니다"
- 게스트의 요청을 거절하는 경우

### action_promise (행동 약속) ⭐️ 중요!
- "~하겠습니다", "~해드리겠습니다", "~드릴게요", "~할게요"
- 호스트/운영팀이 **물리적 행동**을 해야 하는 경우
- 예시:
  - "방문하여 조치하겠습니다" → action_promise
  - "확인 후 연락드리겠습니다" → action_promise
  - "수건 추가로 준비해드릴게요" → action_promise
  - "내일 기사님이 방문합니다" → action_promise

### fee (요금)
- 금액 언급: "추가 요금 2만원", "무료로 해드릴게요"

### change (변경)
- "날짜를 변경해드렸습니다", "인원을 수정했습니다"

### condition (조건부)
- "~하시면 가능합니다", "~경우에만 됩니다"

## topic (주제)

### 체크인/체크아웃
- early_checkin: 얼리체크인
- late_checkout: 레이트체크아웃  
- checkin_time: 체크인 시간 확정
- checkout_time: 체크아웃 시간 확정

### 예약/인원
- guest_count_change: 인원 변경
- reservation_change: 예약 날짜 변경

### 제공/요금
- free_provision: 무료 제공
- extra_fee: 추가 요금
- amenity_request: 어메니티/수건 준비

### 운영 관련
- facility_issue: 시설 문제 조치 (고장, 수리, 점검)
- follow_up: 확인 후 연락 약속
- visit_schedule: 방문 일정 약속

### 민감 토픽
- refund: 환불 관련
- payment: 결제 관련
- compensation: 보상 관련

### 기타
- pet_policy: 반려동물 정책
- special_request: 특별 요청
- other: 분류 불가

## target_time_type & target_date (행동 약속일 때만)

type이 action_promise인 경우, 이행 시점을 파악하세요:

- **explicit**: 명확한 시점이 있음
  - "내일 방문하겠습니다" → explicit, target_date 필수
  - "오늘 중으로 연락드리겠습니다" → explicit
  - "체크인 당일 준비해두겠습니다" → explicit (게스트 체크인 날짜)

- **implicit**: 시점이 불명확함
  - "확인 후 연락드리겠습니다" → implicit (언제인지 모름)
  - "방문하여 조치하겠습니다" → implicit (날짜 미정)
  - "최대한 빠르게" → implicit

**날짜 변환 (오늘 기준):**
- "오늘" → 오늘 날짜
- "내일" → 오늘 + 1일
- "모레" → 오늘 + 2일
- 날짜 모르면 target_date는 null

## 출력 형식

JSON으로만 응답하세요:

```json
{{
  "commitments": [
    {{
      "topic": "facility_issue",
      "type": "action_promise",
      "value": {{"description": "샤워기 문제 방문 조치"}},
      "provenance_text": "방문하여 조치하겠습니다",
      "confidence": 0.9,
      "target_time_type": "implicit",
      "target_date": null
    }}
  ]
}}
```

## 주의사항
- 약속이 없으면: {{"commitments": []}}
- provenance_text는 원문에서 **정확히** 복사
- 하나의 문장에 여러 약속이 있으면 각각 분리
- 인사, 감사, 일반 안내는 약속이 아님
- action_promise와 allowance 구분: "해드릴 수 있습니다"(allowance) vs "해드리겠습니다"(action_promise)"""

    def _build_user_prompt(
        self,
        sent_text: str,
        conversation_context: Optional[str],
        guest_checkin_date: Optional[date] = None,
    ) -> str:
        """사용자 프롬프트 생성"""
        parts = []
        
        # 날짜 컨텍스트 (매우 중요!)
        today = date.today()
        parts.append(f"## 날짜 정보 (필수 참고)")
        parts.append(f"- 오늘 날짜: {today.strftime('%Y-%m-%d')} ({today.year}년 {today.month}월 {today.day}일)")
        if guest_checkin_date:
            parts.append(f"- 게스트 체크인: {guest_checkin_date.strftime('%Y-%m-%d')} ({guest_checkin_date.year}년 {guest_checkin_date.month}월 {guest_checkin_date.day}일)")
            parts.append(f"\n**날짜 해석 규칙:**")
            parts.append(f"- \"9일\", \"9일에\" 등 날짜만 언급 → 체크인 달({guest_checkin_date.month}월)의 해당 일 → {guest_checkin_date.year}-{guest_checkin_date.month:02d}-09")
            parts.append(f"- \"내일\", \"오늘\" → 오늘({today}) 기준으로 계산")
            parts.append(f"- \"체크인 당일\" → {guest_checkin_date.strftime('%Y-%m-%d')}")
        else:
            parts.append(f"- 게스트 체크인: (알 수 없음)")
            parts.append(f"\n**날짜 해석 규칙:**")
            parts.append(f"- 연도 없이 날짜만 언급 시 → {today.year}년 기준")
            parts.append(f"- 현재 월보다 이전 달이면 → 다음 해({today.year + 1}년)")
        parts.append("")
        
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
        target_date = item.get("target_date")  # 🆕
        target_time_type = item.get("target_time_type", "implicit")  # 🆕
        
        # 필수 필드 검증
        if not topic or not type_ or not provenance_text:
            return None
        
        # topic 유효성 검증 - 없으면 other로 (유연하게)
        if topic not in self.ALLOWED_TOPICS:
            topic = CommitmentTopic.OTHER.value
        
        # type 유효성 검증 - 없으면 allowance로 (유연하게)
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
                "action": "action_promise",
                "promise": "action_promise",
            }
            type_ = type_mapping.get(type_, "allowance")  # 기본값 allowance
        
        # confidence 범위 보정
        confidence = max(0.0, min(1.0, float(confidence)))
        
        # value가 dict가 아니면 변환
        if not isinstance(value, dict):
            value = {"description": str(value)}
        
        # target_time_type 유효성 검증
        if target_time_type not in ("explicit", "implicit"):
            target_time_type = "implicit"
        
        # target_date 유효성 검증 (YYYY-MM-DD 형식)
        if target_date:
            try:
                from datetime import datetime
                datetime.strptime(target_date, "%Y-%m-%d")
            except (ValueError, TypeError):
                target_date = None
                target_time_type = "implicit"
        
        return CommitmentCandidate(
            topic=topic,
            type=type_,
            value=value,
            provenance_text=provenance_text,
            confidence=confidence,
            target_date=target_date,
            target_time_type=target_time_type,
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
