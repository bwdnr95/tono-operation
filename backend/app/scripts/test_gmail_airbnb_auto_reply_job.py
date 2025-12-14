# backend/app/scripts/test_gmail_airbnb_auto_reply_job.py
"""
Gmail → Airbnb → IncomingMessage 인제스트 + 자동응답 + 로그 요약 출력 스크립트.

사용 예시:
    cd backend
    python -m app.scripts.test_gmail_airbnb_auto_reply_job \
        --max-results 10 \
        --newer-than-days 1

주의:
    - 실제 Gmail API를 호출하고
    - 실제로 게스트에게 자동응답을 발송할 수 있음 (force 옵션에 주의).
"""

from __future__ import annotations

import argparse
from typing import Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_airbnb_auto_reply_job import (
    run_gmail_airbnb_auto_reply_job,
)
from app.repositories.auto_reply_log_repository import AutoReplyLogRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Gmail→Airbnb auto-reply job and print summary logs."
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Gmail에서 가져올 최대 메일 수 (기본: 20)",
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=3,
        help="며칠 이내 메일만 조회할지 (기본: 3)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 sent=True 인 메시지도 강제로 다시 자동응답을 시도",
    )
    parser.add_argument(
        "--limit-logs",
        type=int,
        default=30,
        help="마지막 자동응답 로그를 몇 건까지 출력할지 (기본: 30)",
    )
    return parser.parse_args()


def print_job_result_summary(result) -> None:
    print("=== Gmail Airbnb Auto-Reply Job Summary ===")
    print(f"  total_parsed                : {result.total_parsed}")
    print(f"  total_ingested              : {result.total_ingested}")
    print(f"  total_target_messages       : {result.total_target_messages}")
    print(f"  total_sent                  : {result.total_sent}")
    print(f"  total_skipped_already_sent  : {result.total_skipped_already_sent}")
    print(f"  total_skipped_no_message    : {result.total_skipped_no_message}")
    print()

    print("=== Per-Message Items ===")
    for item in result.items:
        print(
            f"- gmail_message_id={item.gmail_message_id} "
            f" incoming_message_id={item.incoming_message_id} "
            f" sent={item.sent} skipped={item.skipped} "
            f" reason={item.skip_reason}"
        )
    print()


def print_recent_auto_reply_logs(db: Session, limit: int = 30) -> None:
    repo = AutoReplyLogRepository(db)
    logs = repo.list_recent(limit=limit)

    print(f"=== Recent AutoReply Logs (limit={limit}) ===")
    if not logs:
        print("  (no logs)")
        return

    for log in logs:
        text_preview = (log.reply_text or "").replace("\n", " ")
        if len(text_preview) > 80:
            text_preview = text_preview[:77] + "..."

        print(
            f"[{log.id}] msg_id={log.message_id} "
            f"property={log.property_code or '-'} ota={log.ota or '-'} "
            f"intent={log.intent} fine={log.fine_intent or '-'} "
            f"sent={log.sent} sent_at={log.sent_at} "
            f"edited={log.edited} "
        )
        print(f"   reply: {text_preview}")
    print()


def main() -> None:
    args = parse_args()

    db: Session = SessionLocal()
    try:
        print(
            f"Running auto-reply job: "
            f"max_results={args.max_results}, "
            f"newer_than_days={args.newer_than_days}, "
            f"force={args.force}"
        )

        result = run_gmail_airbnb_auto_reply_job(
            db=db,
            max_results=args.max_results,
            newer_than_days=args.newer_than_days,
            force=args.force,
        )

        print_job_result_summary(result)
        print_recent_auto_reply_logs(db, limit=args.limit_logs)

    finally:
        db.close()


if __name__ == "__main__":
    main()
