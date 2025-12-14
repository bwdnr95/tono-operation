# backend/app/scripts/test_auto_reply.py
from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.auto_reply_service import AutoReplyService
from app.services.airbnb_intent_classifier import AirbnbIntentClassifier
from app.services.llm_intent_classifier import FineGrainedIntentResult


def get_db() -> Session:
    return SessionLocal()


async def run_test(
    *,
    message_id: int,
    ota: Optional[str],
    locale: str,
    property_code: Optional[str],
    use_llm: bool,
    debug: bool,
) -> None:
    db = get_db()
    try:
        # -----------------------------------------
        # 🔍 1) RAW DB 데이터 출력
        # -----------------------------------------
        raw_msg = None
        if debug:
            raw_msg = db.execute(
                text(
                    "SELECT id, gmail_message_id, subject, pure_guest_message, intent, intent_confidence "
                    "FROM incoming_messages WHERE id = :id"
                ),
                {"id": message_id},
            ).fetchone()

            print("\n===== RAW DB MESSAGE =====")
            if raw_msg:
                print(f"id                 : {raw_msg.id}")
                print(f"gmail_message_id   : {raw_msg.gmail_message_id}")
                print(f"subject            : {raw_msg.subject}")
                print(f"pure_guest_message : {raw_msg.pure_guest_message}")
                print(f"intent             : {raw_msg.intent}")
                print(f"intent_confidence  : {raw_msg.intent_confidence}")
            else:
                print("No message found with this id.")
            print("===========================\n")

        # -----------------------------------------
        # 🔍 2) AirbnbIntentClassifier 직접 돌려보기
        #      (현재 하이브리드 Intent 엔진이 이 텍스트를 어떻게 보는지)
        # -----------------------------------------
        if debug and raw_msg and raw_msg.pure_guest_message:
            classifier = AirbnbIntentClassifier()

            hybrid = classifier.classify_airbnb_guest_intent(
                pure_guest_message=raw_msg.pure_guest_message,
                subject=raw_msg.subject,
                snippet=None,
            )

            print("===== HybridIntentResult (AirbnbIntentClassifier) =====")
            print(f"primary_intent     : {hybrid.message_result.intent.name}")
            print(f"primary_confidence : {hybrid.message_result.confidence:.3f}")
            print(f"is_ambiguous       : {hybrid.message_result.is_ambiguous}")
            print(f"reasons            : {hybrid.message_result.reasons}")

            if hybrid.rule_fine_result:
                r = hybrid.rule_fine_result
                print("\n---- Rule Result ----")
                print(f"rule_fine_intent   : {r.fine_intent.name}")
                print(f"rule_primary_intent: {r.primary_intent.name}")
                print(f"rule_confidence    : {r.confidence:.3f}")
                print(f"rule_reasons       : {r.reasons}")

            if hybrid.llm_fine_result:
                l: FineGrainedIntentResult = hybrid.llm_fine_result
                print("\n---- LLM Result ----")
                print(f"llm_fine_intent    : {l.fine_intent.name}")
                print(f"llm_primary_intent : {l.primary_intent.name}")
                print(f"llm_confidence     : {l.confidence:.3f}")
                print(f"llm_reasons        : {l.reasons}")
            print("=======================================================\n")

        # -----------------------------------------
        # 🔥 3) AutoReply 전체 플로우 실행
        # -----------------------------------------
        service = AutoReplyService(db)

        suggestion = await service.suggest_reply_for_message(
            message_id=message_id,
            ota=ota,
            locale=locale,
            property_code=property_code,
            use_llm=use_llm,
        )

        if suggestion is None:
            print(f"[RESULT] message_id={message_id} → suggestion=None (응답 생성 안 됨)")
            return

        print("==== AutoReplySuggestion ====")
        print(f"message_id       : {suggestion.message_id}")
        print(f"intent           : {suggestion.intent.name}")
        print(
            "fine_intent      : "
            f"{suggestion.fine_intent.name if suggestion.fine_intent else None}"
        )
        print(f"intent_confidence: {suggestion.intent_confidence:.3f}")
        print(f"generation_mode  : {suggestion.generation_mode}")
        print(f"action           : {suggestion.action.value}")
        print(f"allow_auto_send  : {suggestion.allow_auto_send}")
        print(f"is_ambiguous     : {suggestion.is_ambiguous}")
        print(f"template_id      : {suggestion.template_id}")
        print("\n---- Reply Text ----")
        print(suggestion.reply_text)
        print("---------------------")

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test TONO AutoReplyService")

    parser.add_argument("--message-id", type=int, required=True)
    parser.add_argument("--ota", type=str, default=None)
    parser.add_argument("--locale", type=str, default="ko")
    parser.add_argument("--property-code", type=str, default=None)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    asyncio.run(
        run_test(
            message_id=args.message_id,
            ota=args.ota,
            locale=args.locale,
            property_code=args.property_code,
            use_llm=not args.no_llm,
            debug=args.debug,
        )
    )


if __name__ == "__main__":
    main()
