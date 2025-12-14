"""
Incoming Messages 파이프라인 단독 테스트 스크립트
- 자동응답 / intent 분석 / staff notification 모두 비활성화
- Gmail → Parse → Save (IncomingMessages) 만 테스트
"""

import asyncio
from datetime import datetime, timedelta

from app.db.session import SessionLocal
from app.adapters.gmail_client import GmailClient
from app.adapters.gmail_airbnb_parser import GmailAirbnbParser
from app.repositories.messages import IncomingMessageRepository


async def fetch_and_save_incoming_messages(
    max_results=10,
    newer_than_days=3,
):
    print("▶ Incoming Messages Fetch Test 시작")

    db = SessionLocal()

    try:
        message_repo = IncomingMessageRepository(db)
        gmail_client = GmailClient()
        parser = GmailAirbnbParser()

        newer_than = datetime.utcnow() - timedelta(days=newer_than_days)

        # ▦ 1) Gmail 메시지 가져오기
        print(f"▶ Gmail fetch (newer_than: {newer_than}, max={max_results})")
        gmail_messages = await gmail_client.fetch_messages(
            max_results=max_results,
            newer_than=newer_than,
        )

        print(f"→ Gmail messages fetched: {len(gmail_messages)}")

        saved_ids = []

        # ▦ 2) 파싱 + 저장
        for raw in gmail_messages:
            parsed = parser.parse(raw)

            if parsed is None:
                print(f"  - Skip (Airbnb 메일 아님): {raw.id}")
                continue

            print(f"  + Parsed Airbnb message: {parsed.gmail_message_id}")

            # DB 저장
            msg = message_repo.create(
                gmail_message_id=parsed.gmail_message_id,
                ota=parsed.ota,
                property_code=parsed.property_code,
                subject=parsed.subject,
                raw_text=parsed.raw_text,
                pure_guest_message=parsed.pure_guest_message,
                sender_actor=parsed.sender_actor,
                actionability=parsed.actionability,

                # ---- 신규 컬럼들 ----
                fine_intent=parsed.fine_intent,
                fine_intent_confidence=parsed.fine_intent_confidence,
                fine_intent_reason=parsed.fine_intent_reason,
                suggested_action=parsed.suggested_action,
                guest_name=parsed.guest_name,
                checkin_date=parsed.checkin_date,
                checkout_date=parsed.checkout_date,
            )

            saved_ids.append(msg.id)

        print(f"▶ 저장된 incoming_messages IDs: {saved_ids}")

    finally:
        db.close()

    print("▶ Incoming Messages Fetch Test 완료")


def main():
    asyncio.run(fetch_and_save_incoming_messages())


if __name__ == "__main__":
    main()
