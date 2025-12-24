# backend/app/services/auto_reply_service.py
"""
TONO AutoReply 엔진 (v3 - Intent 제거, FAQ/Outcome Label 도입)

변경사항:
  - Intent 분류 시스템 완전 제거
  - Template 매칭 제거
  - PropertyProfile + FAQ 기반 LLM 1회 호출
  - Outcome Label 4축 자동 확정
  - used_faq_keys 근거 추적

설계 원칙:
  - Conversation-first: message_id로 호출되어도 conversation context 포함
  - Human-in-the-loop: 자동 발송 없음, 초안만 생성
  - Safety-first: LLM + Rule 보정으로 민감도 확정
  - Data-driven: 모든 판단은 근거(trace)로 남김
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

from sqlalchemy.orm import Session

from app.domain.intents import MessageActor, MessageActionability
from app.repositories.messages import IncomingMessageRepository
from app.repositories.property_profile_repository import PropertyProfileRepository
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.reservation_info_repository import ReservationInfoRepository
from app.services.closing_message_detector import ClosingMessageDetector
from app.core.config import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Outcome Label Enums
# ══════════════════════════════════════════════════════════════

class ResponseOutcome(str, Enum):
    """답변 방식"""
    ANSWERED_GROUNDED = "ANSWERED_GROUNDED"  # 제공된 정보로 명확히 답함
    DECLINED_BY_POLICY = "DECLINED_BY_POLICY"  # 정책상 불가/제한 안내
    NEED_FOLLOW_UP = "NEED_FOLLOW_UP"  # "확인 후 안내"로 마무리
    ASK_CLARIFY = "ASK_CLARIFY"  # 게스트에게 추가 질문 요청


class OperationalOutcome(str, Enum):
    """운영 액션 결과"""
    NO_OP_ACTION = "NO_OP_ACTION"  # 운영 액션 없음
    OC_CREATED = "OC_CREATED"  # OC 생성됨
    OC_UPDATED = "OC_UPDATED"  # 기존 OC 갱신
    OC_RESOLUTION_SUGGESTED = "OC_RESOLUTION_SUGGESTED"  # 해소 제안 생성
    OC_RESOLVED = "OC_RESOLVED"  # resolved/done 처리


class SafetyOutcome(str, Enum):
    """민감도"""
    SAFE = "SAFE"
    SENSITIVE = "SENSITIVE"  # 불만/클레임 가능성
    HIGH_RISK = "HIGH_RISK"  # 환불/보상/법적/안전 이슈


class QualityOutcome(str, Enum):
    """검토 강도"""
    OK_TO_SEND = "OK_TO_SEND"  # 일반 검토로 충분
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # 꼼꼼히 검토 권장
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # 정보 부족/추정 많음


# ══════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════

@dataclass(slots=True)
class OutcomeLabel:
    """Outcome Label 4축 + 근거"""
    response_outcome: ResponseOutcome
    operational_outcome: List[OperationalOutcome]  # 복수 가능
    safety_outcome: SafetyOutcome
    quality_outcome: QualityOutcome
    
    # 근거 필드
    used_faq_keys: List[str] = field(default_factory=list)
    used_profile_fields: List[str] = field(default_factory=list)
    rule_applied: List[str] = field(default_factory=list)
    evidence_quote: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_outcome": self.response_outcome.value,
            "operational_outcome": [o.value for o in self.operational_outcome],
            "safety_outcome": self.safety_outcome.value,
            "quality_outcome": self.quality_outcome.value,
            "used_faq_keys": self.used_faq_keys,
            "used_profile_fields": self.used_profile_fields,
            "rule_applied": self.rule_applied,
            "evidence_quote": self.evidence_quote,
        }


@dataclass(slots=True)
class DraftSuggestion:
    """AI 초안 생성 결과"""
    message_id: int
    reply_text: str
    outcome_label: OutcomeLabel
    generation_mode: str  # "llm" | "static_closing" | "fallback"
    
    # Human Override (초기에는 None)
    human_override: Optional[Dict[str, Any]] = None


# ══════════════════════════════════════════════════════════════
# Main Service
# ══════════════════════════════════════════════════════════════

class AutoReplyService:
    """
    TONO Draft 생성 엔진 (v3)
    
    핵심 메서드:
      - suggest_reply_for_message(): AI 초안 생성 (async)
    
    설계 원칙:
      - PropertyProfile + FAQ가 유일한 지식 소스
      - Intent 분류 없음 (LLM이 직접 판단)
      - Outcome Label 자동 확정 (LLM + Rule 보정)
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._msg_repo = IncomingMessageRepository(db)
        self._property_repo = PropertyProfileRepository(db)
        self._commitment_repo = CommitmentRepository(db)
        self._reservation_repo = ReservationInfoRepository(db)
        self.closing_detector = ClosingMessageDetector()

    # ══════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════

    async def suggest_reply_for_message(
        self,
        *,
        message_id: int,
        locale: str = "ko",
        property_code: Optional[str] = None,
        ota: Optional[str] = None,  # 호환성용 (현재 미사용)
        use_llm: bool = True,  # 호환성용 (현재 항상 LLM 사용)
    ) -> Optional[DraftSuggestion]:
        """
        메시지 1건에 대한 자동응답 초안을 만든다.
        
        Args:
            message_id: 대상 메시지 ID
            locale: 응답 언어
            property_code: 숙소 코드 (없으면 메시지에서 추출)
            ota: OTA 플랫폼 (호환성용, 현재 미사용)
            use_llm: LLM 사용 여부 (호환성용, 현재 항상 True)
            
        Returns:
            DraftSuggestion 또는 None (응답 불필요 시)
        """
        msg = self._msg_repo.get(message_id)
        if not msg:
            return None

        # 게스트 메시지만 처리
        if msg.sender_actor != MessageActor.GUEST:
            logger.info("SKIP(non-guest): message_id=%s", message_id)
            return None

        if msg.actionability != MessageActionability.NEEDS_REPLY:
            logger.info("SKIP(non-needs-reply): message_id=%s", message_id)
            return None

        # property_code 확보
        resolved_property_code = property_code or msg.property_code
        if not resolved_property_code:
            logger.warning("SKIP(no-property-code): message_id=%s", message_id)
            return None

        # 종료 인사 감지 → 간단 응답
        guest_message = (msg.pure_guest_message or "").strip()
        closing = await self.closing_detector.detect(guest_message)
        if closing.is_closing:
            return self._create_closing_suggestion(message_id, locale)

        # 1) Context 구성 (Conversation-first)
        context = self._build_conversation_context(
            message_id=message_id,
            airbnb_thread_id=msg.airbnb_thread_id,
            property_code=resolved_property_code,
        )

        # 2) LLM 호출 (답변 + Outcome Label)
        llm_result = await self._generate_with_llm(
            guest_message=guest_message,
            context=context,
            locale=locale,
        )

        # 3) Rule 보정
        final_outcome = self._apply_rule_corrections(
            llm_outcome=llm_result["outcome_label"],
            guest_message=guest_message,
        )

        return DraftSuggestion(
            message_id=message_id,
            reply_text=llm_result["reply_text"],
            outcome_label=final_outcome,
            generation_mode="llm",
        )

    # ══════════════════════════════════════════════════════════════
    # Context Building (Conversation-first)
    # ══════════════════════════════════════════════════════════════

    def _build_conversation_context(
        self,
        *,
        message_id: int,
        airbnb_thread_id: str,
        property_code: str,
    ) -> Dict[str, Any]:
        """
        LLM에 전달할 컨텍스트 구성
        - PropertyProfile 전체
        - FAQ 전체
        - 최근 대화 (N턴)
        - 확정된 Commitment
        - 예약 정보
        """
        context: Dict[str, Any] = {}
        
        # 1. PropertyProfile
        profile = self._property_repo.get_by_property_code(property_code)
        if profile:
            context["property"] = self._profile_to_dict(profile)
            context["faq_entries"] = profile.faq_entries or []
        
        # 2. 최근 대화 히스토리 (최근 10개)
        recent_messages = self._get_recent_messages(airbnb_thread_id, limit=10)
        context["conversation_history"] = recent_messages
        
        # 3. 확정된 Commitment
        commitments = self._commitment_repo.get_active_by_thread_id(airbnb_thread_id)
        if commitments:
            context["commitments"] = [
                {
                    "type": c.commitment_type,
                    "summary": c.summary,
                    "status": c.status,
                    "created_at": str(c.created_at),
                }
                for c in commitments
            ]
        
        # 4. 예약 정보
        reservation = self._reservation_repo.get_by_airbnb_thread_id(airbnb_thread_id)
        if reservation:
            context["reservation"] = {
                "guest_name": reservation.guest_name,
                "checkin_date": str(reservation.checkin_date) if reservation.checkin_date else None,
                "checkout_date": str(reservation.checkout_date) if reservation.checkout_date else None,
                "guest_count": reservation.guest_count,
                "status": reservation.status,
            }
        
        return context

    def _get_recent_messages(self, airbnb_thread_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """최근 대화 히스토리 조회"""
        from sqlalchemy import select, desc
        from app.domain.models.incoming_message import IncomingMessage
        
        stmt = (
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
            .order_by(desc(IncomingMessage.received_at))
            .limit(limit)
        )
        messages = self._db.execute(stmt).scalars().all()
        
        history = []
        for m in reversed(messages):  # 시간순 정렬
            direction = getattr(m.direction, "value", str(m.direction))
            speaker = "게스트" if "incoming" in direction.lower() else "호스트"
            text = (m.pure_guest_message or m.content or "").strip()
            if text:
                history.append({"speaker": speaker, "message": text})
        
        return history

    def _profile_to_dict(self, profile) -> Dict[str, Any]:
        """PropertyProfile을 dict로 변환 (전체 필드)"""
        return {
            "name": profile.name,
            "property_code": profile.property_code,
            "checkin_from": profile.checkin_from,
            "checkout_until": profile.checkout_until,
            "address_summary": profile.address_summary,
            "location_guide": profile.location_guide,
            "parking_info": profile.parking_info,
            "pet_policy": profile.pet_policy,
            "smoking_policy": profile.smoking_policy,
            "noise_policy": profile.noise_policy,
            "house_rules": profile.house_rules,
            "bbq_guide": profile.bbq_guide,
            "laundry_guide": profile.laundry_guide,
            "heating_usage_guide": profile.heating_usage_guide,
            "wifi_ssid": profile.wifi_ssid,
            "wifi_password": profile.wifi_password,
            "capacity_base": profile.capacity_base,
            "capacity_max": profile.capacity_max,
            "extra_bedding_available": profile.extra_bedding_available,
            "extra_bedding_price_info": profile.extra_bedding_price_info,
            "amenities": profile.amenities,
            "extra_metadata": profile.extra_metadata,
        }

    # ══════════════════════════════════════════════════════════════
    # LLM Generation
    # ══════════════════════════════════════════════════════════════

    async def _generate_with_llm(
        self,
        *,
        guest_message: str,
        context: Dict[str, Any],
        locale: str,
    ) -> Dict[str, Any]:
        """
        LLM으로 답변 + Outcome Label 생성
        """
        api_key = settings.LLM_API_KEY
        if not api_key:
            return self._fallback_result(locale)

        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model_name = settings.LLM_MODEL or "gpt-4o-mini"

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(guest_message, context)

        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            
            raw_content = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)
            
            return self._parse_llm_response(parsed, locale)
            
        except Exception as exc:
            logger.warning("LLM_ERROR: %s", exc)
            return self._fallback_result(locale)

    def _build_system_prompt(self) -> str:
        """
        TONO Superhost Reply System Prompt (v4)
        - Step by Step 사고 유도
        - 게스트 의도 분석 명시화
        - 기존 JSON 구조 호환
        """
        return """당신은 숙소 호스트를 대신해 게스트에게 답장을 작성합니다.

## 목표
게스트의 메시지를 정확히 이해하고, 실제 호스트처럼 자연스럽고 도움이 되는 답변을 작성합니다.

---

## 사고 과정 (반드시 이 순서대로 수행)

### Step 1: 대화 맥락 파악
CONVERSATION_HISTORY를 읽고 파악하세요:
- 이 대화의 주제는 무엇인가?
- 게스트가 연속으로 여러 메시지를 보냈다면, 전체를 하나의 맥락으로 이해한다.
- 호스트가 이미 안내한 내용이 있다면 반복하지 않는다.

### Step 2: 게스트 의도 분석 (가장 중요!)
TARGET_GUEST_MESSAGE를 맥락 안에서 해석하세요:

**질문: 게스트가 원하는 것은 무엇인가?**
- 정보를 알고 싶다 (질문)
- 문제를 해결해달라 (요청)
- 불만/문제를 알리고 싶다 (신고)
- 대화를 마무리하고 싶다 (확인/인사)
- 상황을 공유하고 싶다 (정보 제공)

**질문: 게스트의 감정 상태는?**
- 평온 / 급함 / 걱정 / 불만 / 감사

**주의: 마지막 메시지만 보면 안 됩니다!**
연속된 게스트 메시지가 있다면, 전체 흐름에서 의도를 파악하세요.
예: 앞에서 "거울이 떨어졌어요"라고 했는데 마지막이 "여기 화장실이에요"라면,
의도는 "화장실 위치 확인"이 아니라 "문제 신고 + 위치 설명"입니다.

### Step 3: 답변 전략 결정
게스트 의도에 맞는 답변 방식을 선택하세요:

| 의도 | 답변 방식 | 길이 |
|------|----------|------|
| 정보 질문 | 정확한 정보 제공 | 2-4문장 |
| 문제 해결 요청 | 해결 방안 또는 "확인 후 안내" | 2-4문장 |
| 문제/상황 신고 | 안전 확인 + 사과 + 감사 + 조치 약속 | 2-4문장 |
| 불만 표현 | 진심 어린 사과 + 조치 약속 | 2-4문장 |
| 확인/인사 | 간단한 마무리 | 1-2문장 |

**[문제/상황 신고 상세 가이드]**
게스트가 시설 문제를 알려준 경우 (떨어짐, 고장, 파손, 누수 등):
1. **안전 확인 (첫 문장!)**: "다치신 곳은 없으신가요?", "괜찮으세요?"
2. **사과 (필수!)**: "불편을 드려 정말 죄송합니다", "놀라셨을텐데 죄송해요" - 시설 문제는 호스트 책임이므로 반드시 사과
3. **감사**: "알려주셔서 감사합니다", "피드백 주셔서 감사드려요"
4. **조치 약속**: "현장팀에 전달해서 바로 보완하겠습니다"

예시:
"아이고, 다치신 곳은 없으신가요? ㅠㅠ 많이 놀라셨을텐데 정말 죄송해요. 
알려주셔서 너무 감사합니다! 현장팀에 바로 전달해서 단단히 고정해둘게요 🙏"

### Step 4: 답변 작성
카카오톡으로 대화하듯 자연스럽게 작성하세요.

**필수 원칙:**
- 게스트 의도에 맞는 내용만 답변
- 묻지 않은 정보는 추가하지 않음
- 정보가 없으면 "확인 후 안내드리겠습니다"

**정보 출처:**
- PROPERTY_INFO, FAQ_ENTRIES, RESERVATION에 있는 정보만 사용
- COMMITMENTS에 이전 약속이 있으면 충돌하지 않도록 주의
- 출처에 없는 정보는 추측하지 않음

**톤:**
- 따뜻하고 친근하게, 게스트 감정에 공감
- 이모티콘 적절히 사용 (ㅠㅠ, 🙏, 😊 등)
- 딱딱한 공지문 스타일 금지 ("안내드립니다", "확인되었습니다" 등)
- "~할게요", "~드릴게요" 체 사용

---

## 민감 이슈 처리

환불/보상/리뷰 협박/법적/안전 이슈가 있으면:
- safety_outcome = "HIGH_RISK"
- 단정적 약속 금지
- "확인 후 안내드리겠습니다" 방식으로 안전하게

---

## 예약 상태별 표현 주의 (RESERVATION_STATUS)

- IN_HOUSE (숙박 중): "도착 전", "체크인 전" 금지
- CHECKED_OUT (퇴실 후): "숙박 중", "머무시는 동안" 금지
- UPCOMING (체크인 전): "체크아웃", "퇴실" 금지

---

## 출력 형식 (JSON)

```json
{
  "analysis": {
    "conversation_topic": "현재 대화 주제 (1문장)",
    "guest_intent": "게스트가 원하는 것 (1문장)",
    "response_strategy": "선택한 답변 전략"
  },
  "reply_text": "게스트에게 보낼 답변",
  "outcome": {
    "response_outcome": "ANSWERED_GROUNDED | NEED_FOLLOW_UP | ASK_CLARIFY | DECLINED_BY_POLICY",
    "operational_outcome": ["NO_OP_ACTION"],
    "safety_outcome": "SAFE | SENSITIVE | HIGH_RISK",
    "quality_outcome": "OK_TO_SEND | REVIEW_REQUIRED | LOW_CONFIDENCE"
  },
  "used_faq_keys": ["사용한 FAQ 키"],
  "used_profile_fields": ["사용한 PROPERTY 필드"],
  "evidence_quote": "HIGH_RISK일 때 근거 인용"
}
```

**중요:** analysis를 먼저 작성하고, 그 분석에 맞게 reply_text를 작성하세요."""

    def _build_user_prompt(self, guest_message: str, context: Dict[str, Any]) -> str:
        """
        User Prompt 구성
        - TARGET_GUEST_MESSAGE를 최상단에 명확히 분리
        - RESERVATION_STATUS를 계산하여 마무리 템플릿 힌트 제공
        """
        from datetime import date
        
        # ═══════════════════════════════════════════════════
        # RESERVATION_STATUS 계산
        # ═══════════════════════════════════════════════════
        reservation_status = "UNKNOWN"
        if context.get("reservation"):
            r = context["reservation"]
            status = r.get("status", "").upper()
            checkout_str = r.get("checkout_date")
            checkin_str = r.get("checkin_date")
            
            today = date.today()
            
            # status 필드 우선
            if status in ["CHECKED_OUT", "CHECKOUT", "COMPLETED"]:
                reservation_status = "CHECKED_OUT"
            elif status in ["IN_HOUSE", "STAYING", "CHECKED_IN"]:
                reservation_status = "IN_HOUSE"
            elif status in ["CONFIRMED", "RESERVED", "UPCOMING"]:
                reservation_status = "UPCOMING"
            else:
                # status가 없으면 날짜로 추정
                try:
                    if checkout_str:
                        checkout_date = date.fromisoformat(str(checkout_str)[:10])
                        if checkout_date < today:
                            reservation_status = "CHECKED_OUT"
                        elif checkin_str:
                            checkin_date = date.fromisoformat(str(checkin_str)[:10])
                            if checkin_date <= today <= checkout_date:
                                reservation_status = "IN_HOUSE"
                            elif today < checkin_date:
                                reservation_status = "UPCOMING"
                except:
                    pass
        
        # ═══════════════════════════════════════════════════
        # 1. TARGET_GUEST_MESSAGE (답변 대상)
        # ═══════════════════════════════════════════════════
        target_section = f"""TARGET_GUEST_MESSAGE:
{guest_message.strip()}

RESERVATION_STATUS: {reservation_status}"""

        # ═══════════════════════════════════════════════════
        # 2. CONVERSATION_HISTORY (맥락 파악 필수!)
        # ═══════════════════════════════════════════════════
        history_section = ""
        if context.get("conversation_history"):
            history = context["conversation_history"][-5:]
            
            # 연속 게스트 메시지 감지 (끝에서부터 역순으로)
            consecutive_guest_count = 0
            for h in reversed(history):
                if h['speaker'] == '게스트':
                    consecutive_guest_count += 1
                else:
                    break
            
            # 연속 메시지가 2개 이상이면 강조
            if consecutive_guest_count >= 2:
                lines = [f"[CONVERSATION_HISTORY] ⚠️ 게스트가 연속 {consecutive_guest_count}개 메시지 전송 - 마지막만 보지 말고 전체 맥락에 답변하세요!"]
            else:
                lines = ["[CONVERSATION_HISTORY]"]
            
            for h in history:
                msg_preview = h['message'][:80] + "..." if len(h['message']) > 80 else h['message']
                lines.append(f"  {h['speaker']}: {msg_preview}")
            history_section = "\n".join(lines) + "\n\n"

        # ═══════════════════════════════════════════════════
        # 3. COMMITMENTS (이전 약속 - 충돌 금지)
        # ═══════════════════════════════════════════════════
        commitment_section = ""
        if context.get("commitments"):
            lines = ["[COMMITMENTS] (이전 약속 - 충돌하는 답변 금지)"]
            for c in context["commitments"]:
                lines.append(f"  • {c.get('type', 'N/A')}: {c.get('summary', c.get('provenance_text', 'N/A'))}")
            commitment_section = "\n".join(lines) + "\n\n"

        # ═══════════════════════════════════════════════════
        # 4. RESERVATION (예약 정보)
        # ═══════════════════════════════════════════════════
        reservation_section = ""
        if context.get("reservation"):
            r = context["reservation"]
            reservation_section = f"""[RESERVATION]
  게스트: {r.get('guest_name', '미확인')}
  체크인: {r.get('checkin_date', '미확인')}
  체크아웃: {r.get('checkout_date', '미확인')}
  인원: {r.get('guest_count', '미확인')}명
  상태: {reservation_status}

"""

        # ═══════════════════════════════════════════════════
        # 5. PROPERTY_INFO (숙소 정보)
        # ═══════════════════════════════════════════════════
        property_section = ""
        if context.get("property"):
            p = context["property"]
            # 필수 정보만 추출해서 간결하게
            property_summary = {
                "name": p.get("name"),
                "checkin_from": p.get("checkin_from"),
                "checkout_until": p.get("checkout_until"),
                "address_summary": p.get("address_summary"),
                "parking_info": p.get("parking_info"),
                "pet_policy": p.get("pet_policy"),
                "wifi_ssid": p.get("wifi_ssid"),
                "wifi_password": p.get("wifi_password"),
                "capacity_base": p.get("capacity_base"),
                "capacity_max": p.get("capacity_max"),
            }
            # None 값 제거
            property_summary = {k: v for k, v in property_summary.items() if v}
            
            # 추가 정보가 있으면 포함
            for key in ["location_guide", "house_rules", "smoking_policy", "noise_policy", 
                       "bbq_guide", "laundry_guide", "heating_usage_guide", "extra_bedding_price_info"]:
                if p.get(key):
                    property_summary[key] = p[key]
            
            property_json = json.dumps(property_summary, ensure_ascii=False, indent=2, default=str)
            property_section = f"[PROPERTY_INFO]\n{property_json}\n\n"

        # ═══════════════════════════════════════════════════
        # 6. FAQ_ENTRIES
        # ═══════════════════════════════════════════════════
        faq_section = ""
        if context.get("faq_entries"):
            faq_section = self._format_faq_by_category(context["faq_entries"])

        # ═══════════════════════════════════════════════════
        # 7. 마무리 템플릿 힌트 + 상황별 금지 표현
        # ═══════════════════════════════════════════════════
        closing_hint = ""
        if reservation_status == "CHECKED_OUT":
            closing_hint = """
⚠️ RESERVATION_STATUS=CHECKED_OUT (이미 체크아웃 완료)
- 금지 표현: "숙박 중", "머무시는 동안", "이용 중", "체크인", "도착"
- 게스트가 "감사합니다/수고하세요" 종료 인사를 보낸 경우에만 마무리 인사 사용
"""
        elif reservation_status == "IN_HOUSE":
            closing_hint = """
⚠️ RESERVATION_STATUS=IN_HOUSE (현재 숙박 중 - 게스트가 이미 숙소에 있음!)
- 금지 표현: "도착 전", "체크인 전", "오시기 전", "방문 전", "도착하시면"
- 일반 질문엔 정보만 주고 자연스럽게 끊기. 마무리 인사 붙이지 말 것.
"""
        elif reservation_status == "UPCOMING":
            closing_hint = """
⚠️ RESERVATION_STATUS=UPCOMING (체크인 전)
- 금지 표현: "체크아웃", "퇴실", "머무시는 동안"
"""

        # ═══════════════════════════════════════════════════
        # 최종 조립 (System Prompt Step과 일치)
        # ═══════════════════════════════════════════════════
        return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📜 Step 1: 대화 맥락 파악
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{history_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Step 2: 게스트 의도 분석 (TARGET 메시지)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{target_section}
→ 이 메시지를 위 대화 맥락 안에서 해석하세요.
→ 게스트가 원하는 것은? 감정 상태는?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Step 3: 답변 전략 결정 (참고 정보)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{commitment_section}{reservation_section}{property_section}{faq_section}{closing_hint}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Step 4: 답변 작성
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 분석한 게스트 의도에 맞게 답변
- 시설 문제 신고 시: 안전 확인 → 사과 → 감사 → 조치 약속
- JSON 형식으로 출력"""

    def _format_faq_by_category(self, faq_entries: List[Dict]) -> str:
        """FAQ를 카테고리별로 그룹핑"""
        if not faq_entries:
            return ""
        
        # 카테고리별 그룹핑
        by_category: Dict[str, List] = {}
        for entry in faq_entries:
            cat = entry.get("category", "기타")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(entry)
        
        lines = ["[FAQ - 자주 묻는 질문 (질문과 관련된 항목만 참고하세요)]"]
        for category, entries in by_category.items():
            lines.append(f"\n## {category}")
            for e in entries:
                lines.append(f"- {e['key']}: {e['answer']}")
        
        lines.append("\n⚠️ FAQ에 없는 내용은 '확인 후 안내드리겠습니다'로 답변하세요.")
        
        return "\n".join(lines)

    def _parse_llm_response(self, parsed: Dict, locale: str) -> Dict[str, Any]:
        """LLM 응답 파싱"""
        reply_text = parsed.get("reply_text", "")
        outcome = parsed.get("outcome", {})
        
        # Outcome Label 파싱
        try:
            response_outcome = ResponseOutcome(
                outcome.get("response_outcome", "NEED_FOLLOW_UP")
            )
        except ValueError:
            response_outcome = ResponseOutcome.NEED_FOLLOW_UP
        
        try:
            op_outcomes = outcome.get("operational_outcome", ["NO_OP_ACTION"])
            if isinstance(op_outcomes, str):
                op_outcomes = [op_outcomes]
            operational_outcome = [
                OperationalOutcome(o) for o in op_outcomes 
                if o in OperationalOutcome.__members__
            ]
            if not operational_outcome:
                operational_outcome = [OperationalOutcome.NO_OP_ACTION]
        except (ValueError, TypeError):
            operational_outcome = [OperationalOutcome.NO_OP_ACTION]
        
        try:
            safety_outcome = SafetyOutcome(
                outcome.get("safety_outcome", "SAFE")
            )
        except ValueError:
            safety_outcome = SafetyOutcome.SAFE
        
        try:
            quality_outcome = QualityOutcome(
                outcome.get("quality_outcome", "OK_TO_SEND")
            )
        except ValueError:
            quality_outcome = QualityOutcome.OK_TO_SEND
        
        outcome_label = OutcomeLabel(
            response_outcome=response_outcome,
            operational_outcome=operational_outcome,
            safety_outcome=safety_outcome,
            quality_outcome=quality_outcome,
            used_faq_keys=parsed.get("used_faq_keys", []),
            used_profile_fields=parsed.get("used_profile_fields", []),
            evidence_quote=parsed.get("evidence_quote"),
        )
        
        return {
            "reply_text": reply_text or self._default_fallback_reply(locale),
            "outcome_label": outcome_label,
        }

    # ══════════════════════════════════════════════════════════════
    # Rule Corrections (Safety-first)
    # ══════════════════════════════════════════════════════════════

    def _apply_rule_corrections(
        self,
        llm_outcome: OutcomeLabel,
        guest_message: str,
    ) -> OutcomeLabel:
        """
        Rule 기반 보정 (LLM 판단 + 키워드 룰)
        """
        rules_applied: List[str] = list(llm_outcome.rule_applied)
        safety = llm_outcome.safety_outcome
        quality = llm_outcome.quality_outcome
        evidence = llm_outcome.evidence_quote
        
        msg_lower = guest_message.lower()
        
        # HIGH_RISK 키워드
        high_risk_keywords = [
            "환불", "보상", "배상", "소송", "법적", "경찰", "신고",
            "변호사", "소비자원", "refund", "lawsuit", "police"
        ]
        
        # SENSITIVE 키워드
        sensitive_keywords = [
            "불만", "실망", "화가", "짜증", "최악", "별로", "불쾌",
            "angry", "disappointed", "terrible", "worst",
            "클레임", "컴플레인", "complaint"
        ]
        
        # HIGH_RISK 체크
        for kw in high_risk_keywords:
            if kw in msg_lower:
                if safety != SafetyOutcome.HIGH_RISK:
                    safety = SafetyOutcome.HIGH_RISK
                    rules_applied.append(f"high_risk_keyword:{kw}")
                    evidence = evidence or f"키워드 감지: {kw}"
                quality = QualityOutcome.REVIEW_REQUIRED
                break
        
        # SENSITIVE 체크 (HIGH_RISK가 아닐 때만)
        if safety != SafetyOutcome.HIGH_RISK:
            for kw in sensitive_keywords:
                if kw in msg_lower:
                    if safety == SafetyOutcome.SAFE:
                        safety = SafetyOutcome.SENSITIVE
                        rules_applied.append(f"sensitive_keyword:{kw}")
                        evidence = evidence or f"키워드 감지: {kw}"
                    if quality == QualityOutcome.OK_TO_SEND:
                        quality = QualityOutcome.REVIEW_REQUIRED
                    break
        
        return OutcomeLabel(
            response_outcome=llm_outcome.response_outcome,
            operational_outcome=llm_outcome.operational_outcome,
            safety_outcome=safety,
            quality_outcome=quality,
            used_faq_keys=llm_outcome.used_faq_keys,
            used_profile_fields=llm_outcome.used_profile_fields,
            rule_applied=rules_applied,
            evidence_quote=evidence,
        )

    # ══════════════════════════════════════════════════════════════
    # Fallback & Utilities
    # ══════════════════════════════════════════════════════════════

    def _create_closing_suggestion(self, message_id: int, locale: str) -> DraftSuggestion:
        """종료 인사에 대한 간단 응답"""
        if locale.startswith("ko"):
            reply_text = "감사합니다! 편안한 시간 보내시고, 추가로 필요한 게 있으면 말씀해 주세요. 😊"
        else:
            reply_text = "Thank you! Please let us know if you need anything else. 😊"
        
        outcome_label = OutcomeLabel(
            response_outcome=ResponseOutcome.ANSWERED_GROUNDED,
            operational_outcome=[OperationalOutcome.NO_OP_ACTION],
            safety_outcome=SafetyOutcome.SAFE,
            quality_outcome=QualityOutcome.OK_TO_SEND,
        )
        
        return DraftSuggestion(
            message_id=message_id,
            reply_text=reply_text,
            outcome_label=outcome_label,
            generation_mode="static_closing",
        )

    def _fallback_result(self, locale: str) -> Dict[str, Any]:
        """LLM 실패 시 기본 응답"""
        return {
            "reply_text": self._default_fallback_reply(locale),
            "outcome_label": OutcomeLabel(
                response_outcome=ResponseOutcome.NEED_FOLLOW_UP,
                operational_outcome=[OperationalOutcome.NO_OP_ACTION],
                safety_outcome=SafetyOutcome.SAFE,
                quality_outcome=QualityOutcome.LOW_CONFIDENCE,
            ),
        }

    def _default_fallback_reply(self, locale: str) -> str:
        """기본 폴백 메시지"""
        if locale.startswith("ko"):
            return "안녕하세요, 문의 주셔서 감사합니다. 확인 후 안내드리겠습니다."
        return "Thank you for your message. We will review your request and get back to you."
