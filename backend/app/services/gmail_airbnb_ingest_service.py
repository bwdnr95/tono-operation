from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.gmail_airbnb import (
    fetch_and_parse_recent_airbnb_messages,
)
from app.services.email_ingestion_service import (
    ingest_parsed_airbnb_messages,
)


def fetch_and_ingest_recent_airbnb_messages(
    *,
    db: Session,
    max_results: int = 50,
    newer_than_days: int = 3,
    extra_query: str | None = None,
    dry_run: bool = False,
) -> int:
    """
    1) Gmail API에서 Airbnb 메일을 검색하고 파싱
    2) ingest_parsed_airbnb_messages 를 통해 DB 적재 + Origin/Intent 분류

    반환: 처리한 메시지 개수
    """

    base_query = f"from:airbnb.com newer_than:{newer_than_days}d"
    if extra_query:
        query = f"{base_query} {extra_query}"
    else:
        query = base_query

    print(f"[gmail_airbnb_ingest_service] Gmail 쿼리: {query}")

    # Gmail → Airbnb 파싱 (sync 함수로 가정)
    parsed_messages = fetch_and_parse_recent_airbnb_messages(
        query=query,
        max_results=max_results,
        db=db,  # get_gmail_service 에 db 필요하면 넘김
    )

    if not parsed_messages:
        print("[gmail_airbnb_ingest_service] 처리할 Airbnb 메일이 없습니다.")
        return 0

    print(
        f"[gmail_airbnb_ingest_service] "
        f"Gmail에서 파싱된 Airbnb 메시지 {len(parsed_messages)}건을 가져왔습니다."
    )

    if dry_run:
        print("[gmail_airbnb_ingest_service] dry_run=True → DB 적재 없이 종료합니다.")
        return len(parsed_messages)

    # 🔥 인제스트 서비스 sync 호출
    ingest_parsed_airbnb_messages(
        parsed_messages=parsed_messages,
        db=db,
    )

    print(
        f"[gmail_airbnb_ingest_service] "
        f"{len(parsed_messages)}건의 Airbnb 메시지를 DB에 적재 및 분류했습니다."
    )
    return len(parsed_messages)
