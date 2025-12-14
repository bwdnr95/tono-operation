# backend/app/scripts/send_auto_reply_for_message.py
"""
예시 사용법 (PowerShell):

    cd backend
    python -m app.scripts.send_auto_reply_for_message --message-id 119
"""

import argparse
import traceback

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_fetch_service import get_gmail_service
from app.services.auto_reply_service import AutoReplyService
from app.services.gmail_outbox_service import GmailOutboxService


def get_db() -> Session:
    return SessionLocal()


def main() -> None:
    print("[DEBUG] send_auto_reply_for_message.main() 시작")

    parser = argparse.ArgumentParser()
    parser.add_argument("--message-id", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    print(f"[DEBUG] 파라미터: message_id={args.message_id}, force={args.force}")

    try:
        print("[DEBUG] DB 세션 생성 시도")
        db = get_db()
        print("[DEBUG] DB 세션 생성 완료:", db)

        print("[DEBUG] AutoReplyService 생성 시도")
        auto_reply_service = AutoReplyService(db)
        print("[DEBUG] AutoReplyService 생성 완료:", auto_reply_service)

        print("[DEBUG] Gmail service(get_gmail_service) 생성 시도")
        gmail_service = get_gmail_service(db)
        print("[DEBUG] Gmail service 생성 완료:", gmail_service)

        print("[DEBUG] GmailOutboxService 생성 시도")
        outbox = GmailOutboxService(
            db=db,
            auto_reply_service=auto_reply_service,
            gmail_service=gmail_service,
        )
        print("[DEBUG] GmailOutboxService 생성 완료:", outbox)

        print("[DEBUG] send_auto_reply_for_message 호출 직전")
        suggestion = outbox.send_auto_reply_for_message(
            message_id=args.message_id,
            force=args.force,
        )
        print("[DEBUG] send_auto_reply_for_message 호출 완료, suggestion:", suggestion)

        if suggestion is None:
            print(
                f"[INFO] message_id={args.message_id}: "
                f"전송할 응답이 없거나 이미 전송된 메시지입니다."
            )
            return

        print("==== AutoReplySuggestion ====")
        print(f"message_id       : {suggestion.message_id}")
        print(f"intent           : {suggestion.intent}")
        print(f"fine_intent      : {suggestion.fine_intent}")
        print(f"intent_confidence: {suggestion.intent_confidence:.3f}")
        print(f"generation_mode  : {suggestion.generation_mode}")
        print(f"action           : {suggestion.action}")
        print(f"allow_auto_send  : {suggestion.allow_auto_send}")
        print()
        print("---- Reply Text ----")
        print(suggestion.reply_text)
        print("---------------------")

    except Exception as e:
        print("[ERROR] 스크립트 실행 중 예외 발생:", repr(e))
        traceback.print_exc()


if __name__ == "__main__":
    print("[DEBUG] __main__ 진입")
    main()