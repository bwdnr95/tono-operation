from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_airbnb_ingest_service import (
    fetch_and_ingest_recent_airbnb_messages,
)


def run_ingestion(
    *,
    max_results: int,
    newer_than_days: int,
    extra_query: str | None,
    dry_run: bool,
) -> None:
    db: Session = SessionLocal()
    try:
        print(
            "\n=== TONO Airbnb Gmail → DB 인제스트 시작 ===\n"
            f"- max_results     : {max_results}\n"
            f"- newer_than_days : {newer_than_days}\n"
            f"- extra_query     : {extra_query or '(없음)'}\n"
            f"- dry_run         : {dry_run}\n"
        )

        count = fetch_and_ingest_recent_airbnb_messages(
            db=db,
            max_results=max_results,
            newer_than_days=newer_than_days,
            extra_query=extra_query,
            dry_run=dry_run,
        )

        if not dry_run:
            db.commit()
            print(f"\n✅ 커밋 완료: {count}건의 메시지가 DB에 반영되었습니다.\n")
        else:
            print(f"\n(드라이런) 총 {count}건의 메시지를 처리했으나 커밋은 수행하지 않았습니다.\n")

        print("=== TONO Airbnb Gmail → DB 인제스트 종료 ===\n")

    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gmail에서 Airbnb 메일을 읽어와 DB에 저장하는 TONO 인제스트 스크립트",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="한 번에 가져올 최대 Gmail 메시지 수 (기본: 50)",
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=3,
        help="최근 N일 이내 메일만 가져오기 (기본: 3일)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help='추가 Gmail 검색쿼리 (예: \'subject:"예약"\')',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB에 실제로 저장하지 않고 어떤 메일이 처리될지만 확인",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ingestion(
        max_results=args.max_results,
        newer_than_days=args.newer_than_days,
        extra_query=args.query,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
