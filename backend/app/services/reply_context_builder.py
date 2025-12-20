from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List
from sqlalchemy import select, asc
from sqlalchemy.orm import Session

from app.domain.intents import MessageIntent, FineGrainedIntent
from app.repositories.property_profile_repository import PropertyProfileRepository
from app.repositories.messages import IncomingMessageRepository
from app.repositories.reservation_info_repository import ReservationInfoRepository
from app.repositories.commitment_repository import CommitmentRepository
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.conversation import Conversation


@dataclass(slots=True)
class ReplyContext:
    """
    LLM AutoReply 프롬프트에 들어갈 컨텍스트 구조체.
    """

    message_id: int
    locale: str
    ota: Optional[str]
    property_code: Optional[str]
    primary_intent: MessageIntent
    fine_intent: Optional[FineGrainedIntent]
    pure_guest_message: str
    property_profile: Optional[Dict[str, Any]]
    
    # 🔹 예약 정보 (reservation_info에서 가져옴)
    reservation_context: Optional[str] = None  # LLM에게 전달할 문자열 형태
    
    # 🆕 Commitment 정보 (이전에 확정한 약속들)
    commitment_context: Optional[str] = None  # LLM에게 전달할 문자열 형태


class ReplyContextBuilder:
    """
    Message + PropertyProfile + Intent를 묶어 LLM에 넘길 컨텍스트를 만든다.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._msg_repo = IncomingMessageRepository(db)
        self._property_repo = PropertyProfileRepository(db)
        self._reservation_repo = ReservationInfoRepository(db)
        self._commitment_repo = CommitmentRepository(db)

    def build_for_message(
        self,
        *,
        message_id: int,
        primary_intent: MessageIntent,
        fine_intent: Optional[FineGrainedIntent],
        locale: str,
        explicit_property_code: Optional[str] = None,
    ) -> ReplyContext:
        msg = self._msg_repo.get_by_id(message_id)

        if not msg:
            raise ValueError(f"IncomingMessage(id={message_id}) not found")

        property_code = explicit_property_code or msg.property_code

        property_profile_dict: Optional[Dict[str, Any]] = None
        if property_code:
            profile = self._property_repo.get_by_property_code(property_code)
            if profile:
                property_profile_dict = self._select_fields_by_intent(
                    profile=profile,
                    primary_intent=primary_intent,
                    fine_intent=fine_intent,
                )

        pure_guest_message = msg.pure_guest_message or ""

        return ReplyContext(
            message_id=msg.id,
            locale=locale,
            ota=msg.ota,
            property_code=property_code,
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            pure_guest_message=pure_guest_message,
            property_profile=property_profile_dict,
        )

    def build_for_conversation(
        self,
        *,
        airbnb_thread_id: str,
        primary_intent: MessageIntent,
        fine_intent: Optional[FineGrainedIntent],
        locale: str,
        explicit_property_code: Optional[str] = None,
        max_messages: int = 20,
    ) -> ReplyContext:
        msgs = (
            self._db.execute(
                select(IncomingMessage)
                .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
                .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
            )
            .scalars()
            .all()
        )
        if not msgs:
            raise ValueError(f"No messages for airbnb_thread_id={airbnb_thread_id}")

        msgs = msgs[-max_messages:]

        transcript_lines: list[str] = []
        last_guest: Optional[IncomingMessage] = None

        for m in msgs:
            text = (m.pure_guest_message or m.content or "").strip()
            if not text:
                continue

            direction = getattr(m.direction, "value", None) or str(getattr(m, "direction", "incoming"))
            direction = direction.split(".")[-1]
            speaker = "게스트" if direction == "incoming" else "호스트"
            transcript_lines.append(f"{speaker}: {text}")

            if direction == "incoming":
                last_guest = m

        if not last_guest:
            raise ValueError("No guest(incoming) message found in thread")

        conversation_text = "\n".join(transcript_lines).strip()
        if not conversation_text:
            raise ValueError("Conversation transcript is empty")

        # ✅ 기존 build_for_message 로직 재사용(중요: Intent import 문제/타입 문제 방지)
        base = self.build_for_message(
            message_id=last_guest.id,
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            locale=locale,
            explicit_property_code=explicit_property_code,
        )
        
        # 🔹 reservation_info 조회 → LLM context 문자열 생성
        reservation_context: Optional[str] = None
        reservation_info = self._reservation_repo.get_by_airbnb_thread_id(airbnb_thread_id)
        if reservation_info:
            reservation_context = reservation_info.to_llm_context()
        
        # 🆕 commitment 조회 → LLM context 문자열 생성
        commitment_context: Optional[str] = None
        commitments = self._commitment_repo.get_active_by_thread_id(airbnb_thread_id)
        if commitments:
            lines = ["[이전에 확정한 약속들]"]
            for c in commitments:
                lines.append(f"- {c.to_llm_context()}")
            commitment_context = "\n".join(lines)

        # ✅ 차이는 pure_guest_message에 transcript 넣는 것 + reservation_context + commitment_context 추가
        return ReplyContext(
            message_id=base.message_id,
            locale=base.locale,
            ota=base.ota,
            property_code=base.property_code,
            primary_intent=base.primary_intent,
            fine_intent=base.fine_intent,
            pure_guest_message=conversation_text,
            property_profile=base.property_profile,
            reservation_context=reservation_context,
            commitment_context=commitment_context,
        )
    # ------------------------------------------------------------------
    # 내부: Intent에 따라 PropertyProfile에서 어떤 필드를 꺼낼지 결정
    # ------------------------------------------------------------------

    def _select_fields_by_intent(
        self,
        *,
        profile: Any,  # SQLAlchemy 모델
        primary_intent: MessageIntent,
        fine_intent: Optional[FineGrainedIntent],
    ) -> Dict[str, Any]:
        """
        LLM이 쓰게 할 필드만 골라서 dict로 만들어 준다.
        (PropertyProfile 전체를 던지지 않고, Intent에 맞는 부분만)
        """

        base: Dict[str, Any] = {
            "name": profile.name,
            "locale": profile.locale,
            "address_summary": profile.address_summary,
            "house_rules": profile.house_rules,
            "extra_metadata": profile.extra_metadata,
        }

        # 체크인 계열
        if primary_intent == MessageIntent.CHECKIN_QUESTION:
            base.update(
                {
                    "checkin_from": profile.checkin_from,
                    #"checkin_to": profile.checkin_to,
                    "access_guide": profile.access_guide,
                    "parking_info": profile.parking_info,
                }
            )

        # 체크아웃 계열
        if primary_intent == MessageIntent.CHECKOUT_QUESTION:
            base.update(
                {
                    "checkout_until": profile.checkout_until,
                    "access_guide": profile.access_guide,
                }
            )

        # 위치/주차 계열 (LOCATION_QUESTION 하나로 처리, 주차도 포함)
        if primary_intent == MessageIntent.LOCATION_QUESTION:
            base.update(
                {
                    "parking_info": profile.parking_info,
                    "location_guide": profile.location_guide,
                    "access_guide": profile.access_guide,
                }
            )

        # 편의시설 계열
        if primary_intent == MessageIntent.AMENITY_QUESTION:
            base.update(
                {
                    "amenities": profile.amenities,
                    "space_overview": profile.space_overview,
                }
            )

        # 반려동물 정책
        if primary_intent == MessageIntent.PET_POLICY_QUESTION:
            base.update(
                {
                    "pet_policy": profile.pet_policy,
                    "house_rules": profile.house_rules,
                }
            )

        # 하우스 룰 계열 (흡연/소음 등 FineIntent로 더 세밀히 가능)
        if primary_intent == MessageIntent.HOUSE_RULE_QUESTION:
            base.update(
                {
                    "smoking_policy": profile.smoking_policy,
                    "noise_policy": profile.noise_policy,
                    "house_rules": profile.house_rules,
                }
            )

        return base
