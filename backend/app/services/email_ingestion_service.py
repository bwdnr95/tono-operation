from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.domain.intents import (
    MessageActor,
    MessageActionability,
)
from app.services.airbnb_message_origin_classifier import (
    classify_airbnb_message_origin,
)
from app.services.airbnb_intent_classifier import (
    classify_airbnb_guest_intent,
)
from app.services.airbnb_guest_message_extractor import (
    extract_guest_message_segment,
)
from app.repositories.messages import IncomingMessageRepository
from app.services.message_intent_label_service import (
    MessageIntentLabelService,
)


def ingest_parsed_airbnb_messages(
    *,
    parsed_messages: Iterable,  # adapters/gmail_airbnb.py 의 ParsedInternalMessage 리스트
    db: Session,
) -> None:
    """
    Airbnb용으로 파싱된 Gmail 메시지들을 DB에 적재.

    - Origin(게스트/호스트/시스템)
    - Intent(게스트 메시지인 경우)
    - pure_guest_message (추출된 순수 게스트 메시지)
    - SYSTEM Intent 라벨(message_intent_labels) 자동 기록
    """
    repo = IncomingMessageRepository(db)
    label_service = MessageIntentLabelService(db)

    for parsed in parsed_messages:
        origin = classify_airbnb_message_origin(
            decoded_text_body=getattr(parsed, "decoded_text_body", None),
            decoded_html_body=getattr(parsed, "decoded_html_body", None),
            subject=getattr(parsed, "subject", None),
            snippet=getattr(parsed, "snippet", None),
        )

        pure_guest_message = extract_guest_message_segment(
            getattr(parsed, "decoded_text_body", "") or ""
        )

        intent_result = None
        if (
            origin.actor == MessageActor.GUEST
            and origin.actionability == MessageActionability.NEEDS_REPLY
        ):
            intent_result = classify_airbnb_guest_intent(
                decoded_text_body=getattr(parsed, "decoded_text_body", None),
                subject=getattr(parsed, "subject", None),
                snippet=getattr(parsed, "snippet", None),
            )

        # 🔥 레포지토리 메서드는 sync 로 호출
        msg = repo.create_from_parsed(
            gmail_message_id=getattr(parsed, "id", None),
            thread_id=getattr(parsed, "thread_id", None),
            subject=getattr(parsed, "subject", None),
            from_email=getattr(parsed, "from_email", None),
            text_body=getattr(parsed, "decoded_text_body", None),
            html_body=getattr(parsed, "decoded_html_body", None),
            received_at=getattr(parsed, "received_at", None),
            origin=origin,
            intent_result=intent_result,
            pure_guest_message=pure_guest_message,
        )

        # ✅ SYSTEM Intent 라벨 자동 기록 (Intent가 있을 때만)
        if intent_result is not None:
            label_service.add_system_label_only(
                message_id=msg.id,
                intent=intent_result.intent,
                confidence=intent_result.confidence,
            )
