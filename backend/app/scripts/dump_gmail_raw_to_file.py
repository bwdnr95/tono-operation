# backend/app/scripts/dump_gmail_raw_to_file.py
"""
Gmail API raw response를 txt 파일로 저장하는 스크립트.

- Gmail에서 Airbnb 관련 메일을 가져와서
  BASIC INFO / HEADERS / PAYLOAD(full) 을 한 번에 txt 파일로 남긴다.
- 콘솔에서 로그가 중간에 짤리는 문제를 피하기 위한 용도.

사용 예시:

    cd backend

    # 최근 3일치 Airbnb 메일 5개, logs/gmail_raw_YYYYMMDD_HHMMSS.txt 로 저장
    python -m app.scripts.dump_gmail_raw_to_file ^
        --max-results 5 ^
        --newer-than-days 3

    # 특정 쿼리로만
    python -m app.scripts.dump_gmail_raw_to_file ^
        --max-results 3 ^
        --query "from:airbnb.com [오픈특가]"

    # 특정 Gmail message id 한 개만
    python -m app.scripts.dump_gmail_raw_to_file ^
        --message-id 19afcc607a59423a
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from googleapiclient.discovery import Resource
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_fetch_service import get_gmail_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gmail API raw response를 txt 파일로 저장",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="가져올 메시지 개수 (message-id 미지정 시에만 사용, 기본: 5)",
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=7,
        help='기본 검색 쿼리에서 사용할 newer_than:x 일 (기본: 7일)',
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help=(
            "Gmail 검색 쿼리 (예: 'from:airbnb.com'). "
            "지정하지 않으면 'from:airbnb.com newer_than:Xd' 로 자동 생성."
        ),
    )
    parser.add_argument(
        "--message-id",
        type=str,
        default=None,
        help="특정 Gmail message id 하나만 직접 덤프하고 싶을 때 사용",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="logs",
        help="로그 파일을 저장할 디렉토리 (backend/app 기준, 기본: logs)",
    )
    parser.add_argument(
        "--output-filename",
        type=str,
        default=None,
        help=(
            "파일 이름 직접 지정 (예: gmail_raw_debug.txt). "
            "지정하지 않으면 gmail_raw_YYYYMMDD_HHMMSS.txt 로 생성."
        ),
    )
    return parser.parse_args()


def _build_default_query(newer_than_days: int) -> str:
    return f"from:airbnb.com newer_than:{newer_than_days}d"


def _open_output_file(output_dir: str, output_filename: Optional[str]) -> Path:
    base_dir = Path(__file__).resolve().parent  # .../backend/app/scripts
    logs_dir = (base_dir / output_dir).resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)

    if output_filename:
        filename = output_filename
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gmail_raw_{ts}.txt"

    path = logs_dir / filename
    return path


def _writeln(f: TextIO, text: str = "") -> None:
    f.write(text + "\n")


def _pretty_dump_json(f: TextIO, obj, title: Optional[str] = None) -> None:
    if title:
        _writeln(f, f"===== {title} =====")
    _writeln(f, json.dumps(obj, ensure_ascii=False, indent=2))
    _writeln(f)


def dump_single_message(service: Resource, message_id: str, f: TextIO, index: int) -> None:
    """
    단일 Gmail message id 에 대해 BASIC INFO / HEADERS / PAYLOAD 를 파일에 기록.
    """
    full_msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    _writeln(f, "=" * 80)
    _writeln(f, f"[{index}] Gmail message id: {message_id}")
    _writeln(f, "=" * 80)

    basic = {
        "id": full_msg.get("id"),
        "threadId": full_msg.get("threadId"),
        "snippet": full_msg.get("snippet"),
    }
    _pretty_dump_json(f, basic, title="BASIC INFO")

    payload = full_msg.get("payload", {}) or {}
    headers = payload.get("headers", []) or []

    _pretty_dump_json(f, headers, title="HEADERS")
    _pretty_dump_json(f, payload, title="PAYLOAD (full)")

    # 필요하면 전체 full_msg 도 남기고 싶을 때:
    # _pretty_dump_json(f, full_msg, title="FULL MESSAGE")


def dump_message_list(
    service: Resource,
    max_results: int,
    query: str,
    f: TextIO,
) -> None:
    """
    검색 결과 여러 건을 순회하면서 파일에 덤프.
    """
    _writeln(f, "=== Gmail 메시지 목록 조회 ===")
    _writeln(f, f"query      : {query}")
    _writeln(f, f"maxResults : {max_results}")
    _writeln(f)

    resp = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=max_results,
            labelIds=["INBOX"],
        )
        .execute()
    )

    msg_metas = resp.get("messages", []) or []
    _writeln(f, f"총 {len(msg_metas)}개 메시지 메타데이터를 가져왔습니다.\n")

    if not msg_metas:
        return

    for idx, meta in enumerate(msg_metas, start=1):
        msg_id = meta.get("id")
        dump_single_message(service, msg_id, f=f, index=idx)


def main() -> None:
    args = parse_args()

    db: Session = SessionLocal()
    try:
        service: Resource = get_gmail_service(db)

        output_path = _open_output_file(
            output_dir=args.output_dir,
            output_filename=args.output_filename,
        )

        with output_path.open("w", encoding="utf-8") as f:
            if args.message_id:
                dump_single_message(
                    service=service,
                    message_id=args.message_id,
                    f=f,
                    index=1,
                )
            else:
                query = args.query or _build_default_query(args.newer_than_days)
                dump_message_list(
                    service=service,
                    max_results=args.max_results,
                    query=query,
                    f=f,
                )

        print(f"[dump_gmail_raw_to_file] Gmail raw 응답을 파일로 저장했습니다.")
        print(f"  -> {output_path}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
