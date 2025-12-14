# backend/app/scripts/test_full_incoming_pipeline.py
"""
incoming_messages 파이프라인 결과 확인용 스크립트.

사용 플로우 예시:

1) (선택) 기존 데이터 정리
   - PGAdmin 등에서 아래 SQL 실행:
       TRUNCATE TABLE public.incoming_messages RESTART IDENTITY CASCADE;

2) Gmail → Airbnb Auto-Reply Job 실행
   - 이미 있는 스크립트 재사용:
       cd backend
       python -m app.scripts.test_gmail_airbnb_auto_reply_job ^
           --max-results 10 ^
           --newer-than-days 1

   ※ 이 단계에서 실제 자동응답이 발송될 수 있으니,
      테스트 계정/테스트 기간에서만 사용하는 걸 추천.

3) 이 스크립트 실행으로 DB에 잘 들어갔는지 확인
   - 최근 N건의 incoming_messages를 조회해서
     intent / fine_intent / suggested_action / guest_name / checkin_date 등 출력.
"""

from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="incoming_messages 파이프라인 결과를 확인하는 스크립트"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="최근 몇 건의 incoming_messages 를 조회할지 (기본: 20)",
    )
    return parser.parse_args()


def print_incoming_messages(db: Session, limit: int = 20) -> None:
    """
    incoming_messages 테이블에서 최근 N건을 조회해서
    intent / fine_intent / suggested_action / guest_name / checkin/checkout_date 를 출력.
    """
    query = text(
        """
        SELECT
            id,
            gmail_message_id,
            received_at,
            ota,
            ota_listing_id,
            ota_listing_name,
            property_code,
            intent,
            intent_confidence,
            fine_intent,
            fine_intent_confidence,
            fine_intent_reasons,
            suggested_action,
            allow_auto_send,
            last_auto_reply_at,
            guest_name,
            checkin_date,
            checkout_date
        FROM public.incoming_messages
        ORDER BY id DESC
        LIMIT :limit
        """
    )

    rows = db.execute(query, {"limit": limit}).mappings().all()

    print(f"=== Recent incoming_messages (limit={limit}) ===")
    if not rows:
        print("  (no rows)")
        return

    for row in rows:
        def _short(text_val: Any, max_len: int = 80) -> str:
            if text_val is None:
                return "-"
            s = str(text_val).replace("\n", " ")
            return (s[: max_len - 3] + "...") if len(s) > max_len else s

        print(
            f"[{row['id']}]"
            f" gmail={row['gmail_message_id']}"
            f" received_at={row['received_at']}"
        )
        print(
            f"   ota={row['ota'] or '-'}"
            f" listing_id={row['ota_listing_id'] or '-'}"
            f" listing_name={_short(row['ota_listing_name'], 40)}"
            f" property={row['property_code'] or '-'}"
        )
        print(
            f"   intent={row['intent'] or '-'}"
            f" (conf={row['intent_confidence']})"
        )
        print(
            f"   fine_intent={row['fine_intent'] or '-'}"
            f" (conf={row['fine_intent_confidence']})"
        )
        print(
            f"   suggested_action={row['suggested_action'] or '-'}"
            f" allow_auto_send={row['allow_auto_send']}"
            f" last_auto_reply_at={row['last_auto_reply_at']}"
        )
        print(
            f"   guest_name={row['guest_name'] or '-'}"
            f" checkin_date={row['checkin_date']}"
            f" checkout_date={row.get('checkout_date')}"
        )
        print(
            f"   fine_intent_reasons={_short(row['fine_intent_reasons'], 120)}"
        )
        print("-" * 80)


def main() -> None:
    args = parse_args()

    db: Session = SessionLocal()
    try:
        print_incoming_messages(db, limit=args.limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()
