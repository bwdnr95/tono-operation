# backend/app/services/email_ingestion_service.py
from __future__ import annotations

from typing import Iterable
import logging

from sqlalchemy.orm import Session

from app.domain.models.conversation import ConversationChannel
from app.services.conversation_thread_service import ConversationService

from app.domain.intents import (
    MessageActor,
    MessageActionability,
)
from app.services.airbnb_message_origin_classifier import (
    classify_airbnb_message_origin,
)
from app.services.airbnb_guest_message_extractor import (
    extract_guest_message_segment,
)

# ✅ (원래 레포에 존재하는 Intent 분류기 사용)
from app.services.airbnb_intent_classifier import AirbnbIntentClassifier, HybridIntentResult

from app.repositories.messages import IncomingMessageRepository
from app.services.message_intent_label_service import MessageIntentLabelService
from app.repositories.ota_listing_mapping_repository import OtaListingMappingRepository

logger = logging.getLogger(__name__)

_airbnb_intent_classifier = AirbnbIntentClassifier()


def ingest_parsed_airbnb_messages(
    db: Session,
    parsed_messages: Iterable,
) -> None:
    """
    ParsedInternalMessage들을 incoming_messages로 저장 (idempotent) + Intent 라벨 저장

    CURRENT PHASE (v1.3):
    - 모든 Incoming Message는 thread_id 필수
    - (gmail, thread_id) 기반으로 Conversation upsert
    """
    repo = IncomingMessageRepository(db)
    label_service = MessageIntentLabelService(db)
    mapping_repo = OtaListingMappingRepository(db)

    for parsed in parsed_messages:
        gmail_message_id = getattr(parsed, "gmail_message_id", None)
        if not gmail_message_id:
            continue

        thread_id = getattr(parsed, "thread_id", None)
        if not thread_id:
            logger.warning(
                "Airbnb ingestion: skip missing thread_id gmail_message_id=%s",
                gmail_message_id,
            )
            continue

        existing = repo.get_by_gmail_message_id(gmail_message_id)
        if existing is not None:
            logger.info(
                "Airbnb ingestion: skip already ingested gmail_message_id=%s (incoming_message_id=%s)",
                gmail_message_id,
                existing.id,
            )
            continue

        decoded_text_body = getattr(parsed, "decoded_text_body", None)
        decoded_html_body = getattr(parsed, "decoded_html_body", None)

        origin = classify_airbnb_message_origin(
            decoded_text_body=decoded_text_body,
            decoded_html_body=decoded_html_body,
            subject=getattr(parsed, "subject", None),
            snippet=getattr(parsed, "snippet", None),
        )

        pure_guest_message = extract_guest_message_segment(decoded_text_body or "")

        intent_result = None
        if origin.sender_actor == MessageActor.GUEST and origin.actionability == MessageActionability.NEEDS_REPLY:
            try:
                hybrid_result: HybridIntentResult = _airbnb_intent_classifier.classify_airbnb_guest_intent(
                    pure_guest_message=pure_guest_message,
                    subject=getattr(parsed, "subject", None),
                    snippet=getattr(parsed, "snippet", None),
                )
                intent_result = hybrid_result.message_result
            except Exception as exc:
                logger.warning("Intent classify failed: %s", exc)

        property_code = getattr(parsed, "property_code", None)
        ota = getattr(parsed, "ota", None)
        ota_listing_id = getattr(parsed, "ota_listing_id", None)
        if not property_code and ota and ota_listing_id:
            try:
                mapping = mapping_repo.get_by_ota_listing_id(
                    ota=ota,
                    listing_id=ota_listing_id,
                    active_only=True,
                )
                if mapping is not None:
                    property_code = mapping.property_code
            except Exception as exc:
                logger.warning(
                    "Failed to map (ota, listing_id) to property_code: ota=%s listing_id=%s err=%s",
                    ota,
                    ota_listing_id,
                    exc,
                )

        msg = repo.create_from_parsed(
            gmail_message_id=gmail_message_id,
            thread_id=thread_id,
            subject=getattr(parsed, "subject", None),
            from_email=getattr(parsed, "from_email", None),
            received_at=getattr(parsed, "received_at", None),
            origin=origin,
            intent_result=intent_result,
            pure_guest_message=pure_guest_message,
            ota=ota,
            ota_listing_id=ota_listing_id,
            ota_listing_name=getattr(parsed, "ota_listing_name", None),
            property_code=property_code,
            guest_name=getattr(parsed, "guest_name", None),
            checkin_date=getattr(parsed, "checkin_date", None),
            checkout_date=getattr(parsed, "checkout_date", None),
        )

        # ✅ Conversation upsert (v1.3: (gmail, thread_id))
        ConversationService(db).upsert_for_thread(
            channel=ConversationChannel.gmail,
            thread_id=msg.thread_id,
            last_message_id=msg.id,
        )

        if intent_result is not None:
            label_service.add_system_label_only(
                message_id=msg.id,
                intent=intent_result.intent,
                confidence=intent_result.confidence,
            )
