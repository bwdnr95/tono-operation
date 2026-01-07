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
    ANSWERED_GROUNDED = "ANSWERED_GROUNDED"  # 제공된 정보로 명확히 답함 (used_faq_keys 필수)
    DECLINED_BY_POLICY = "DECLINED_BY_POLICY"  # 정책상 불가/제한 안내
    NEED_FOLLOW_UP = "NEED_FOLLOW_UP"  # "확인 후 안내"로 마무리
    ASK_CLARIFY = "ASK_CLARIFY"  # 게스트에게 추가 질문 요청
    CLOSING_MESSAGE = "CLOSING_MESSAGE"  # 종료/감사 인사 응답
    GENERAL_RESPONSE = "GENERAL_RESPONSE"  # property_profiles 참고 없이 일반 응대


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
    used_faq_keys: List[str] = field(default_factory=list)  # property_profiles 컬럼명 또는 faq_entries key
    rule_applied: List[str] = field(default_factory=list)
    evidence_quote: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_outcome": self.response_outcome.value,
            "operational_outcome": [o.value for o in self.operational_outcome],
            "safety_outcome": self.safety_outcome.value,
            "quality_outcome": self.quality_outcome.value,
            "used_faq_keys": self.used_faq_keys,
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

    def __init__(self, db: Session, openai_client=None) -> None:
        self._db = db
        self._msg_repo = IncomingMessageRepository(db)
        self._property_repo = PropertyProfileRepository(db)
        self._commitment_repo = CommitmentRepository(db)
        self._reservation_repo = ReservationInfoRepository(db)
        self.closing_detector = ClosingMessageDetector()
        
        # OpenAI 클라이언트 (DI)
        self._client = openai_client
        # 자동응답 생성용 모델 (품질 중요)
        self._model = settings.LLM_MODEL_REPLY or settings.LLM_MODEL or "gpt-4.1"

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

        # 🆕 연속 게스트 메시지 병합 (호스트 답변 없이 연속된 메시지들)
        current_message = (msg.pure_guest_message or "").strip()
        unanswered_messages = self._get_unanswered_guest_messages(
            airbnb_thread_id=msg.airbnb_thread_id,
            current_message_id=message_id,
        )
        
        if unanswered_messages:
            # 연속 메시지가 있으면 병합
            guest_message = unanswered_messages
            logger.info(
                f"AUTO_REPLY: Merged consecutive guest messages for message_id={message_id}"
            )
        else:
            guest_message = current_message

        # 종료 인사 감지 → 간단 응답 (현재 메시지만으로 판단)
        closing = await self.closing_detector.detect(current_message)
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
                    "topic": c.topic,
                    "type": c.type,
                    "summary": c.provenance_text,
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

    def _get_unanswered_guest_messages(self, airbnb_thread_id: str, current_message_id: int) -> str:
        """
        호스트 답변 없이 연속된 게스트 메시지들을 병합해서 반환
        
        조건:
        1. 호스트 답변이 없는 연속 메시지
        2. actionability == NEEDS_REPLY인 메시지만
        3. 30분 이내의 메시지만
        """
        from datetime import timedelta
        from sqlalchemy import select, desc
        from app.domain.models.incoming_message import IncomingMessage
        
        MAX_MERGE_INTERVAL = timedelta(minutes=30)
        
        # 최근 메시지 20개 조회 (넉넉히)
        stmt = (
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
            .order_by(desc(IncomingMessage.received_at))
            .limit(20)
        )
        messages = list(self._db.execute(stmt).scalars().all())
        
        # 시간순 정렬 (오래된 것 → 최신)
        messages = list(reversed(messages))
        
        # 현재 메시지 위치 찾기
        current_idx = None
        for i, m in enumerate(messages):
            if m.id == current_message_id:
                current_idx = i
                break
        
        if current_idx is None:
            return ""
        
        # 현재 메시지부터 역순으로, 호스트 답변 전까지 게스트 메시지 수집
        unanswered_messages = []
        prev_time = None
        
        for i in range(current_idx, -1, -1):
            m = messages[i]
            direction = getattr(m.direction, "value", str(m.direction))
            is_guest = "incoming" in direction.lower()
            
            if not is_guest:
                # 호스트 답변 만나면 중단
                break
            
            # 시간 간격 체크 (30분 초과면 중단)
            if prev_time and m.received_at:
                time_gap = prev_time - m.received_at
                if time_gap > MAX_MERGE_INTERVAL:
                    break
            
            # NEEDS_REPLY인 메시지만 병합
            if m.actionability == MessageActionability.NEEDS_REPLY:
                text = (m.pure_guest_message or m.content or "").strip()
                if text:
                    unanswered_messages.insert(0, text)  # 앞에 추가 (시간순 유지)
            
            if m.received_at:
                prev_time = m.received_at
        
        if len(unanswered_messages) <= 1:
            return ""  # 연속 메시지가 아님
        
        # 여러 메시지를 하나로 병합
        return "\n---\n".join(unanswered_messages)

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
        if not self._client:
            logger.warning("AUTO_REPLY_SERVICE: No OpenAI client available")
            return self._fallback_result(locale)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(guest_message, context)

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                top_p=1.0,
                presence_penalty=0.1,
                frequency_penalty=0.0,
            )
            
            raw_content = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)
            
            return self._parse_llm_response(parsed, locale)
            
        except Exception as exc:
            logger.warning("LLM_ERROR: %s", exc)
            return self._fallback_result(locale)

    def _build_system_prompt(self) -> str:
        """
        TONO Superhost Reply System Prompt (v5 - gpt-4.1 최적화)
        
        변경사항:
        - 규칙 나열 → 원칙 중심으로 간소화
        - INTERNAL CONSIDERATION 도입 (LLM 스스로 판단)
        - 연속 메시지 맥락 이해 지시 추가
        - 핵심 예시 3개로 압축
        """
        return """ROLE
너는 숙소 운영자를 대신해 게스트에게 실제 사람이 보낸 것처럼 자연스럽고 
신뢰감 있는 답장을 작성한다. 목표는 게스트가 추가 질문 없이, 
이 메시지 하나로 바로 이해하고 행동할 수 있게 하는 것이다.

답변은:
- 짧고 명확해야 하며
- 따뜻하지만 과장되면 안 되고
- 고객센터 공지문이나 AI 같은 말투가 나면 실패다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERNAL CONSIDERATION (출력하지 말 것)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
답변을 작성하기 전에, 아래 사항을 고려한다. 이 판단 과정은 절대 출력하지 않는다.

1. 답변 대상 파악
   - LAST_GUEST_MESSAGE와 CONVERSATION_HISTORY를 함께 본다.
   - 게스트가 연속으로 보낸 메시지들은 하나의 맥락으로 이해하고 전체 의도에 답변한다.
   - 단, 호스트가 이미 답변한 이슈는 반복하지 않는다.

2. 게스트의 현재 상태 판단 (중요!)
   RESERVATION_STATUS는 날짜 기준 추정값이다. 실제 상태는 메시지에서 파악:
   - "퇴실했습니다", "나왔어요" → 이미 체크아웃
   - "도착했어요", "들어왔어요" → 이미 체크인
   - "가는 중이에요", "몇시에 도착해요" → 아직 체크인 전
   - 시설/물품 관련 질문 → 숙소에 있음
   
   RESERVATION_STATUS와 메시지 내용이 다르면, 메시지 내용을 따른다.

3. 단정적으로 답할 수 있는가?
   사실/규정/시간/금액은 반드시 아래 정보에서만:
   - PROPERTY_INFO, FAQ_ENTRIES, RESERVATION, COMMITMENTS
   위 정보에 없으면 → "확인 후 안내드리겠습니다."
   COMMITMENTS와 충돌 가능성 있으면 → 단정하지 말고 "확인 후 안내"

4. 안전 이슈 감지
   파손·부상·사고·환불·보상·법적 표현이 있으면:
   ① 안부 먼저 ② 짧은 공감 ③ 조치 또는 "확인 후 안내"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WRITING STYLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
정중하고 부드러운 존댓말을 사용한다.

원칙:
- 문장 끝은 "~습니다", "~입니다", "~세요", "~에요"로 마무리
- 따뜻하지만 격식있는 느낌 유지
- 이모지는 :) 😊 정도만 절제해서 사용 (문장당 최대 1개)

금지:
- 반말, 줄임말, "~요~" 같은 과한 친근함
- 앵무새 반복: "~라고 하셨는데", "~라는 말씀 잘 알겠습니다"
- 형식적 표현: "문의 감사드립니다", "안내드립니다", "확인되었습니다"
- 장문 공지문 스타일

권장 흐름:
① 짧은 인사 ("안녕하세요!")
② 핵심 정보
③ (선택) 부드러운 안내 ("확인 부탁드립니다")
④ 짧은 마무리 ("감사합니다 :)")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[파손 신고] → response_outcome: ANSWERED_GROUNDED, safety_outcome: SENSITIVE
게스트: "유리컵이 깨졌어요 죄송합니다"
❌ "유리컵이 깨졌다는 말씀 잘 알겠습니다."
✅ "다치신 곳은 없으세요? 불편드려 죄송합니다. 괜찮으시다면 다행이에요. 파편은 조심히 치워두시고, 나머지는 저희가 정리하겠습니다 :)"

[퇴실/감사 인사] → response_outcome: CLOSING_MESSAGE (used_faq_keys: [])
게스트: "퇴실했습니다!" / "감사합니다!" / "잘 쉬었어요"
❌ "체크인은 오후 3시부터 가능합니다..." (ANSWERED_GROUNDED 잘못 분류)
✅ "이용해 주셔서 감사합니다. 안전하게 귀가하셨으면 좋겠습니다. 다음에 또 뵐 수 있으면 좋겠습니다 😊"

[일반 질문] → response_outcome: ANSWERED_GROUNDED, used_faq_keys: ["wifi_ssid", "wifi_password"]
게스트: "와이파이 비밀번호가 뭐에요?"
❌ "와이파이 비밀번호는 ABC123입니다."
✅ "안녕하세요! 비밀번호는 ABC123입니다. 네트워크는 'TONO_5G' 선택해주시면 됩니다 :)"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASK_CLARIFY RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
정말로 답변이 불가능한 경우에만 질문한다.
- 질문은 1개만
- 질문 전에 왜 필요한지 1문장 설명

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
아래 JSON 형식으로만 출력한다.

{
  "reply_text": "게스트에게 보낼 최종 답장",
  "outcome": {
    "response_outcome": "ANSWERED_GROUNDED | DECLINED_BY_POLICY | NEED_FOLLOW_UP | ASK_CLARIFY | CLOSING_MESSAGE | GENERAL_RESPONSE",
    "operational_outcome": ["NO_OP_ACTION"],
    "safety_outcome": "SAFE | SENSITIVE | HIGH_RISK",
    "quality_outcome": "OK_TO_SEND | REVIEW_REQUIRED | LOW_CONFIDENCE"
  },
  "used_faq_keys": [],
  "evidence_quote": ""
}

필드 설명:
- used_faq_keys: 답변 작성 시 참고한 PROPERTY_INFO 또는 FAQ_ENTRIES의 키/컬럼명 (배열)
  예: ["wifi_ssid", "wifi_password"], ["parking_info"], ["checkin_from", "checkout_until"]
  PROPERTY_INFO에서 참고했으면 해당 컬럼명, FAQ에서 참고했으면 해당 key 값을 넣는다.
  정보를 참고하지 않았으면 빈 배열 []

outcome 기준:
- ANSWERED_GROUNDED: PROPERTY_INFO 또는 FAQ_ENTRIES 정보를 참고하여 구체적으로 답함
  → 반드시 used_faq_keys에 참고한 컬럼/키를 명시해야 함
  → used_faq_keys가 비어있으면 ANSWERED_GROUNDED 사용 불가
- GENERAL_RESPONSE: property_profiles 참고 없이 일반적인 응대/확인
  → "네 확인했습니다", "알겠습니다", "좋은 시간 되세요" 등 정보 참고 불필요한 응대
  → used_faq_keys는 빈 배열 []
- DECLINED_BY_POLICY: 정책상 불가/제한 안내
- NEED_FOLLOW_UP: 정보 부족으로 "확인 후 안내"
- ASK_CLARIFY: 게스트에게 추가 질문 요청
- CLOSING_MESSAGE: 종료/감사/퇴실 인사에 대한 응답 (used_faq_keys 불필요)
- SENSITIVE: 불만/클레임 가능성
- HIGH_RISK: 환불/보상/법적/안전 이슈 → REVIEW_REQUIRED 필수

⚠️ ANSWERED_GROUNDED vs GENERAL_RESPONSE vs CLOSING_MESSAGE 구분:
- "체크인은 3시입니다" → ANSWERED_GROUNDED (checkin_time 참고)
- "네 입금 확인했습니다" → GENERAL_RESPONSE (정보 참고 없음, 단순 확인 응대)
- "예약 변경 요청 확인했습니다" → GENERAL_RESPONSE (정보 참고 없음, 단순 확인 응대)
- "좋은 시간 되세요", "감사합니다" → CLOSING_MESSAGE (종료/감사 인사)

⚠️ CLOSING_MESSAGE 판단 기준:
게스트가 "감사합니다", "잘 쉬었어요", "퇴실했습니다", "나왔어요", "좋았어요" 등
종료/감사/퇴실 인사를 보냈고, 특별한 질문이나 요청이 없는 경우.
이 경우 답변도 감사/마무리 인사로 작성하고, response_outcome은 반드시 CLOSING_MESSAGE로 설정."""

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
            
            # status가 명시적으로 체크아웃/체크인 완료인 경우
            if status in ["CHECKED_OUT", "CHECKOUT", "COMPLETED"]:
                reservation_status = "CHECKED_OUT"
            elif status in ["IN_HOUSE", "STAYING", "CHECKED_IN"]:
                reservation_status = "IN_HOUSE"
            else:
                # confirmed, reserved 등은 날짜로 세부 판단
                try:
                    checkin_date = None
                    checkout_date = None
                    
                    if checkin_str:
                        checkin_date = date.fromisoformat(str(checkin_str)[:10])
                    if checkout_str:
                        checkout_date = date.fromisoformat(str(checkout_str)[:10])
                    
                    if checkout_date and checkout_date < today:
                        # 체크아웃 날짜가 지남
                        reservation_status = "CHECKED_OUT"
                    elif checkout_date and checkout_date == today:
                        # 체크아웃 당일
                        reservation_status = "CHECKOUT_DAY"
                    elif checkin_date and checkin_date > today:
                        # 체크인 전
                        reservation_status = "UPCOMING"
                    elif checkin_date and checkin_date == today:
                        # 체크인 당일
                        reservation_status = "CHECKIN_DAY"
                    elif checkin_date and checkout_date and checkin_date < today < checkout_date:
                        # 숙박 중
                        reservation_status = "IN_HOUSE"
                except:
                    pass
        
        # ═══════════════════════════════════════════════════
        # 1. GUEST_MESSAGES (답변 대상 - 연속 메시지 병합됨)
        # ═══════════════════════════════════════════════════
        target_section = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 GUEST_MESSAGES (호스트 답변 없이 연속된 게스트 메시지 전체)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{guest_message.strip()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 위 메시지들에 포함된 모든 질문/요청에 답변하세요.
RESERVATION_STATUS: {reservation_status}
"""

        # ═══════════════════════════════════════════════════
        # 2. CONVERSATION_HISTORY (이전 대화 참고용)
        # ═══════════════════════════════════════════════════
        history_section = ""
        if context.get("conversation_history"):
            lines = ["[CONVERSATION_HISTORY - 이미 답변된 내용은 반복하지 말 것]"]
            for h in context["conversation_history"][-5:]:
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
                topic = c.get('topic', 'N/A')
                ctype = c.get('type', 'N/A')
                summary = c.get('summary', c.get('provenance_text', 'N/A'))
                lines.append(f"  • [{topic}] {ctype}: {summary}")
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
⚠️ RESERVATION_STATUS=CHECKED_OUT (체크아웃 완료)
- 게스트가 이미 숙소를 떠난 상태
- 금지 표현: "숙박 중", "머무시는 동안", "이용 중", "체크인", "도착"
"""
        elif reservation_status == "CHECKOUT_DAY":
            closing_hint = """
⚠️ RESERVATION_STATUS=CHECKOUT_DAY (체크아웃 당일)
- 게스트가 아직 숙소에 있을 수도, 이미 나갔을 수도 있음
- 메시지 내용으로 판단: "퇴실했습니다", "나왔어요" → 이미 나감 / "아직 있어요", 시설 질문 → 아직 있음
- 판단 안 되면 중립적으로 답변
"""
        elif reservation_status == "IN_HOUSE":
            closing_hint = """
⚠️ RESERVATION_STATUS=IN_HOUSE (숙박 중)
- 게스트가 현재 숙소에 있음
- 금지 표현: "도착 전", "체크인 전", "오시기 전", "방문 전", "도착하시면"
"""
        elif reservation_status == "CHECKIN_DAY":
            closing_hint = """
⚠️ RESERVATION_STATUS=CHECKIN_DAY (체크인 당일)
- 게스트가 아직 안 왔을 수도, 이미 도착했을 수도 있음
- 메시지 내용으로 판단: "도착했어요", "들어왔어요" → 이미 도착 / "몇시에 가요", "가는 중" → 아직 안 옴
- 판단 안 되면 중립적으로 답변
"""
        elif reservation_status == "UPCOMING":
            closing_hint = """
⚠️ RESERVATION_STATUS=UPCOMING (체크인 전)
- 게스트가 아직 도착하지 않은 상태
- 금지 표현: "체크아웃", "퇴실", "머무시는 동안"
"""

        # ═══════════════════════════════════════════════════
        # 최종 조립
        # ═══════════════════════════════════════════════════
        return f"""{target_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 참고 정보 (아래 정보만 사용, 없으면 "확인 후 안내드리겠습니다")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{history_section}{commitment_section}{reservation_section}{property_section}{faq_section}{closing_hint}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
위 정보를 바탕으로 답변을 JSON으로 작성하세요.
실제 호스트가 카톡 보내듯 자연스럽게. 인사 → 정보 → 부드러운 확인/권유 → 짧은 마무리 순으로."""

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
            rule_applied=rules_applied,
            evidence_quote=evidence,
        )

    # ══════════════════════════════════════════════════════════════
    # Fallback & Utilities
    # ══════════════════════════════════════════════════════════════

    def _create_closing_suggestion(self, message_id: int, locale: str) -> DraftSuggestion:
        """종료 인사에 대한 간단 응답"""
        if locale.startswith("ko"):
            reply_text = "감사합니다! 남은 일정 간 행복만 가득하시길 기도하겠습니다 :) ! 추가로 필요한 게 있으시면 언제든 말씀해주세요! 😊"
        else:
            reply_text = "Thank you! Please let us know if you need anything else. 😊"
        
        outcome_label = OutcomeLabel(
            response_outcome=ResponseOutcome.CLOSING_MESSAGE,
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
