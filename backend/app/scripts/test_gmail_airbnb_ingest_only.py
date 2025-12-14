# backend/app/scripts/test_gmail_airbnb_ingest_only.py
"""
Gmail → Airbnb 메일 파싱 → incoming_messages 에만 적재하는 안전한 테스트 스크립트.

❗️중요:
    - 이 스크립트는 "자동응답 발송"을 전혀 하지 않는다.
    - 오직 Gmail에서 Airbnb 메일을 가져와 파싱하고,
      incoming_messages 테이블에 저장되는지 확인하는 용도다.

사용 예시:
    cd backend

    # 최근 1일치 Airbnb 메일 최대 10건만 인제스트
    python -m app.scripts.test_gmail_airbnb_ingest_only ^
        --max-results 10 ^
        --newer-than-days 1

옵션:
    --max-results      : Gmail API에서 가져올 최대 메시지 수 (기본 10)
    --newer-than-days  : 최근 며칠 내 메일만 대상으로 할지 (기본 3일)
    --query            : Gmail 검색 쿼리를 직접 지정하고 싶을 때
                         (지정하지 않으면 from:airbnb.com newer_than:Xd 사용)
    --dry-run          : True일 경우 DB에 쓰지 않고, 파싱 결과만 로그로 본다.
    --print-limit      : 인제스트 후 최근 N개 incoming_messages를 콘솔에 보여준다 (기본 20개)
"""

from __future__ import annotations

import argparse
from typing import Optional

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_airbnb_ingest_service import (
    fetch_and_ingest_recent_airbnb_messages,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gmail → Airbnb → incoming_messages 인제스트 ONLY 테스트 스크립트",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Gmail API에서 가져올 최대 메시지 수 (기본: 10)",
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=3,
        help="최근 며칠 내 메일만 검색할지 (기본: 3일)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Gmail 검색 쿼리 (예: 'from:airbnb.com'). "
             "지정하지 않으면 from:airbnb.com newer_than:Xd 로 자동 생성.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="파싱만 하고 DB에는 적재하지 않음 (gmail_airbnb_ingest_service의 dry_run 사용).",
    )
    parser.add_argument(
        "--print-limit",
        type=int,
        default=20,
        help="인제스트 후, 최근 N개 incoming_messages를 콘솔에 출력 (기본: 20)",
    )
    return parser.parse_args()


def print_recent_incoming_messages(db: Session, limit: int = 20) -> None:
    """
    incoming_messages 에서 최근 N개 레코드를 가져와
    guest_name / checkin_date / checkout_date 등 메타데이터를 콘솔에 보여준다.
    """
    # checkout_date 컬럼이 없다면 이 SELECT에서 에러가 날 수 있음.
    # 그 경우 checkout_date 부분만 제거해서 쓰면 된다.
    sql = sa_text(
        """
        SELECT
            id,
            gmail_message_id,
            from_email,
            guest_name,
            checkin_date,
            -- checkout_date 가 없으면 아래 줄을 주석 처리하거나 컬럼을 추가해야 함
            checkout_date,
            subject,
            received_at
        FROM incoming_messages
        ORDER BY id DESC
        LIMIT :limit
        """
    )

    result = db.execute(sql, {"limit": limit})

    print("\n=== Recent incoming_messages (limit={}) ===".format(limit))
    rows = result.fetchall()
    if not rows:
        print("  (no rows)")
        return

    for row in rows:
        # row 를 dict 처럼 접근 가능하다고 가정 (SQLAlchemy Row)
        print(
            f"- id={row.id} | gmail_message_id={row.gmail_message_id}\n"
            f"  from_email   : {row.from_email}\n"
            f"  guest_name   : {row.guest_name}\n"
            f"  checkin_date : {row.checkin_date}\n"
            f"  checkout_date: {getattr(row, 'checkout_date', None)}\n"
            f"  received_at  : {row.received_at}\n"
            f"  subject      : {row.subject}\n"
        )


def main() -> None:
    args = parse_args()

    db: Session = SessionLocal()
    try:
        print("[test_gmail_airbnb_ingest_only] 시작")
        print(f"  max_results     = {args.max_results}")
        print(f"  newer_than_days = {args.newer_than_days}")
        print(f"  query           = {args.query!r}")
        print(f"  dry_run         = {args.dry_run}")

        # gmail_airbnb_ingest_service 를 통해
        # 1) Gmail 에서 Airbnb 메일 가져오기
        # 2) gmail_airbnb 파서로 파싱
        # 3) (dry_run 이 아니면) incoming_messages 에 적재
        ingested_count = fetch_and_ingest_recent_airbnb_messages(
            db=db,
            max_results=args.max_results,
            newer_than_days=args.newer_than_days,
            extra_query=args.query,
            dry_run=args.dry_run,
        )

        print(
            f"[test_gmail_airbnb_ingest_only] "
            f"fetch_and_ingest_recent_airbnb_messages 결과: {ingested_count}건 처리"
        )

        if args.dry_run:
            print(
                "[test_gmail_airbnb_ingest_only] dry_run=True 이므로 "
                "DB에는 아무 레코드도 쓰지 않았습니다."
            )
        else:
            # DB에 실제로 어떤 값이 들어갔는지 확인
            db.commit()
            print_recent_incoming_messages(db, limit=args.print_limit)

        print("[test_gmail_airbnb_ingest_only] 완료")

    finally:
        db.close()


if __name__ == "__main__":
    main()
