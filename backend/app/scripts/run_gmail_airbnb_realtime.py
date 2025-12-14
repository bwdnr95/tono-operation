# backend/app/scripts/run_gmail_airbnb_realtime.py
from __future__ import annotations

import argparse
import time
import logging

from app.scripts import run_gmail_airbnb_ingestion

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TONO Gmail → Airbnb 실시간(주기적) 인입 워커",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="각 인입 사이의 대기 시간 (초). 기본 60초",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Gmail API 호출 시 최대 메시지 수 (기본 50)",
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=2,
        help="몇 일 이내의 메일만 조회할지 (기본 2일 이내)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="추가 Gmail 검색 쿼리 (예: 'from:airbnb.com')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB에 적재하지 않고 어떤 메일이 처리될지만 로그로 출력",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info(
        "Starting realtime Airbnb Gmail ingestion loop: interval=%s sec, max_results=%s, newer_than_days=%s",
        args.interval_seconds,
        args.max_results,
        args.newer_than_days,
    )

    while True:
        try:
            run_gmail_airbnb_ingestion.run_ingestion(
                max_results=args.max_results,
                newer_than_days=args.newer_than_days,
                extra_query=args.query,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            logger.exception("Realtime ingestion iteration failed: %s", exc)

        logger.info("Sleeping %s seconds before next ingestion...", args.interval_seconds)
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
