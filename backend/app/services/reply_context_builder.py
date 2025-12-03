from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from app.domain.intents import MessageIntent
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.property_profile import PropertyProfile
from app.repositories.property_profile_repository import PropertyProfileRepository


@dataclass
class ReplyContext:
    """
    LLM에 전달할 컨텍스트 DTO.

    - property: 숙소 관련 지식
    - message: 게스트 메시지 및 메일 메타 정보
    - intent: TONO 분류 Intent 정보
    """

    property: dict[str, Any] | None
    message: dict[str, Any]
    intent: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReplyContextBuilder:
    """
    IncomingMessage + MessageIntent + property_code를 받아
    LLM 컨텍스트(JSON)를 구성하는 역할만 담당.
    """

    def __init__(self, property_repo: PropertyProfileRepository):
        self.property_repo = property_repo

    # --- public API ---

    def build_for_message(
        self,
        *,
        message: IncomingMessage,
        intent: MessageIntent | None,
        property_code: str | None,
    ) -> ReplyContext:
        """
        - property_code 기준으로 PropertyProfile 조회
        - Intent 종류에 맞게 필요한 필드만 추출
        - message / intent 관련 메타 포함
        """

        profile: PropertyProfile | None = None
        if property_code:
            profile = self.property_repo.get_by_property_code(property_code)

        property_ctx = (
            self._build_property_context(profile=profile, intent=intent)
            if profile
            else None
        )
        message_ctx = self._build_message_context(message=message)
        intent_ctx = self._build_intent_context(intent=intent)

        return ReplyContext(
            property=property_ctx,
            message=message_ctx,
            intent=intent_ctx,
        )

    # --- 내부 헬퍼들 ---

    def _build_property_context(
        self,
        *,
        profile: PropertyProfile,
        intent: MessageIntent | None,
    ) -> dict[str, Any]:
        base = {
            "property_code": profile.property_code,
            "name": profile.name,
            "locale": profile.locale,
        }

        common = {
            "checkin_from": profile.checkin_from,
            "checkin_to": profile.checkin_to,
            "checkout_until": profile.checkout_until,
            "parking_info": profile.parking_info,
            "pet_policy": profile.pet_policy,
            "smoking_policy": profile.smoking_policy,
            "noise_policy": profile.noise_policy,
            "amenities": profile.amenities,
            "address_summary": profile.address_summary,
            "location_guide": profile.location_guide,
            "access_guide": profile.access_guide,
            "house_rules": profile.house_rules,
            "space_overview": profile.space_overview,
            "extra_metadata": profile.extra_metadata,
        }

        if intent is None:
            # Intent 모르면 통째로 제공
            return {**base, **common}

        name = intent.name

        if name == "CHECKIN_QUESTION":
            fields = [
                "checkin_from",
                "checkin_to",
                "checkout_until",
                "access_guide",
                "location_guide",
                "house_rules",
            ]
        elif name == "PET_POLICY_QUESTION":
            fields = ["pet_policy", "house_rules"]
        elif name == "LOCATION_QUESTION":
            fields = ["address_summary", "location_guide", "amenities"]
        elif name == "AMENITY_QUESTION":
            fields = ["amenities", "space_overview"]
        else:
            # GENERAL_QUESTION, OTHER 등
            fields = [
                "space_overview",
                "amenities",
                "parking_info",
                "pet_policy",
                "location_guide",
                "house_rules",
                "noise_policy",
            ]

        filtered = {k: v for k, v in common.items() if k in fields}
        return {**base, **filtered}

    def _build_message_context(self, *, message: IncomingMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "gmail_message_id": message.gmail_message_id,
            "thread_id": message.thread_id,
            "subject": message.subject,
            "from_email": message.from_email,
            "received_at": (
                message.received_at.isoformat() if message.received_at else None
            ),
            # V2 모델 기준으로 존재한다고 가정
            "text_body": getattr(message, "text_body", None),
            "html_body": getattr(message, "html_body", None),
            "pure_guest_message": getattr(message, "pure_guest_message", None),
            "sender_actor": message.sender_actor.name,
            "actionability": message.actionability.name,
        }

    def _build_intent_context(self, *, intent: MessageIntent | None) -> dict[str, Any]:
        if intent is None:
            return {
                "intent": None,
                "description": None,
            }
        return {
            "intent": intent.name,
            "description": getattr(intent, "value", None),
        }
