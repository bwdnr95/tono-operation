# backend/app/scripts/debug_gmail_raw_messages.py
"""
Gmail API raw response 디버그용 스크립트.

- Gmail에서 메시지 목록을 가져온 뒤
  각 메시지에 대한 "full" response JSON 을 그대로 출력한다.
- guest_name / 체크인/체크아웃 파싱 전에
  실제 Subject / From / payload 구조를 눈으로 확인하는 용도.

사용 예시:

    cd backend

    # 최근 3일치 Airbnb 메일 3개만 보기
    python -m app.scripts.debug_gmail_raw_messages \
        --max-results 3 \
        --newer-than-days 3

    # 특정 쿼리로만 (예: Airbnb 알림 + 특정 리스팅 이름 포함)
    python -m app.scripts.debug_gmail_raw_messages \
        --max-results 2 \
        --query "from:airbnb.com [오픈특가]"

    # 특정 Gmail message id 만 직접 보기
    python -m app.scripts.debug_gmail_raw_messages \
        --message-id xxxxxxxxxxxxxxxxx
"""

from __future__ import annotations

import argparse
import json
from typing import Optional

from googleapiclient.discovery import Resource
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_fetch_service import get_gmail_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gmail API raw response 디버그 스크립트",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        help="가져올 메시지 개수 (message-id 미지정 시에만 사용, 기본: 3)",
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=7,
        help="최근 며칠 내 메일만 검색할지 (query 미지정 시, 기본: 7일)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help='Gmail 검색 쿼리 (예: \'from:airbnb.com\'). '
             '지정하지 않으면 "from:airbnb.com newer_than:Xd" 로 자동 생성.',
    )
    parser.add_argument(
        "--message-id",
        type=str,
        default=None,
        help="특정 Gmail message id 하나만 직접 가져와서 출력하고 싶을 때 사용",
    )
    return parser.parse_args()


def _build_default_query(newer_than_days: int) -> str:
    # TONO 기본값: Airbnb 도메인 메일만
    return f"from:airbnb.com newer_than:{newer_than_days}d"


def _pretty_print_json(obj, title: Optional[str] = None) -> None:
    if title:
        print(f"===== {title} =====")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print()


def debug_single_message(service: Resource, message_id: str) -> None:
    """
    단일 Gmail message id 에 대해 "full" response JSON 출력.
    """
    full_msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    _pretty_print_json(
        {
            "id": full_msg.get("id"),
            "threadId": full_msg.get("threadId"),
            "snippet": full_msg.get("snippet"),
        },
        title="BASIC INFO",
    )

    # headers / payload 만 따로 본다.
    payload = full_msg.get("payload", {}) or {}
    headers = payload.get("headers", []) or []

    _pretty_print_json(headers, title="HEADERS")
    _pretty_print_json(payload, title="PAYLOAD (full)")

    # 필요하면 전체 response 를 통째로 보고 싶을 때:
    # _pretty_print_json(full_msg, title="FULL MESSAGE JSON")


def debug_message_list(
    service: Resource,
    max_results: int,
    query: str,
) -> None:
    """
    검색 쿼리로 message list 를 가져오고, 각 메시지에 대해 debug_single_message 호출.
    """
    print("=== Gmail 메시지 목록 조회 ===")
    print(f" query      : {query}")
    print(f" maxResults : {max_results}")
    print()

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
    print(f"총 {len(msg_metas)}개 메시지 메타데이터를 가져왔습니다.\n")

    if not msg_metas:
        return

    for idx, meta in enumerate(msg_metas, start=1):
        msg_id = meta.get("id")
        print("=" * 80)
        print(f"[{idx}] Gmail message id: {msg_id}")
        print("=" * 80)
        debug_single_message(service, msg_id)


def main() -> None:
    args = parse_args()

    db: Session = SessionLocal()
    try:
        service: Resource = get_gmail_service(db)

        if args.message_id:
            # 특정 message id 만 디버그
            debug_single_message(service, args.message_id)
        else:
            # 쿼리 기본값 구성
            query = args.query or _build_default_query(args.newer_than_days)
            debug_message_list(
                service=service,
                max_results=args.max_results,
                query=query,
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()
