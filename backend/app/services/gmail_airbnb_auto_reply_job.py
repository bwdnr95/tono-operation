# backend/app/services/gmail_airbnb_auto_reply_job.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.adapters.gmail_airbnb import (
    fetch_and_parse_recent_airbnb_messages,
    ParsedInternalMessage,
)
from app.repositories.messages import IncomingMessageRepository
from app.services.email_ingestion_service import ingest_parsed_airbnb_messages
from app.services.gmail_fetch_service import get_gmail_service
from app.services.gmail_outbox_service import GmailOutboxService
from app.services.auto_reply_service import AutoReplyService


@dataclass
class AutoReplyJobItem:
    """
    개별 Gmail 메시지에 대해 Job이 어떤 행동을 했는지 요약.
    """
    gmail_message_id: str
    incoming_message_id: Optional[int]
    sent: bool          # 실제 Gmail 발송 여부
    skipped: bool       # 이미 발송됨 / 메시지 미존재 / 기타 이유로 스킵
    skip_reason: Optional[str]


@dataclass
class AutoReplyJobResult:
    """
    전체 잡 실행 결과 요약.
    """
    total_parsed: int
    total_ingested: int
    total_target_messages: int   # 실제로 AutoReply를 시도한 메시지 수
    total_sent: int
    total_skipped_already_sent: int
    total_skipped_no_message: int
    items: List[AutoReplyJobItem]


def run_gmail_airbnb_auto_reply_job(
    *,
    db: Session,
    max_results: int = 50,
    newer_than_days: int = 3,
    extra_query: str | None = None,
    query: str | None = None,
    force: bool = False,
) -> AutoReplyJobResult:
    """
    1) Gmail에서 Airbnb 관련 메일을 최근 N건 가져와 파싱
    2) incoming_messages 에 인제스트 (idempotent)
    3) 아직 AutoReply가 발송되지 않은 메시지에 대해:
       - AutoReplyService 로 답변 생성
       - GmailOutboxService 로 실제 발송
       - auto_reply_logs 에 기록

    force=True 인 경우:
      - 이미 AutoReplyLog.sent=True 인 케이스까지 강제로 다시 시도
      (실무에서는 일반적으로 False 권장)
    """

    # ------------------------------------------------------------------
    # 1) Gmail → Airbnb 파싱 (기존 어댑터 재사용)
    # ------------------------------------------------------------------
    parsed_messages: List[ParsedInternalMessage] = fetch_and_parse_recent_airbnb_messages(
        db=db,
        max_results=max_results,
        newer_than_days=newer_than_days,
        extra_query=extra_query,
        query=query,
        dry_run=False,  # 실제로 가져와서 쓸 것이므로 dry_run=False
    )
    total_parsed = len(parsed_messages)

    # ------------------------------------------------------------------
    # 2) DB 인제스트 (기존 email_ingestion_service 재사용)
    # ------------------------------------------------------------------
    ingest_parsed_airbnb_messages(
        parsed_messages=parsed_messages,
        db=db,
    )
    # ingestion 내부에서 gmail_message_id 기준 idempotent 처리함
    # (이미 동일 gmail_message_id가 있으면 skip) :contentReference[oaicite:5]{index=5}

    msg_repo = IncomingMessageRepository(db)

    # ------------------------------------------------------------------
    # 3) AutoReply + Gmail 발송 준비
    # ------------------------------------------------------------------
    gmail_service = get_gmail_service(db)  # 토큰은 google_tokens 테이블에서 읽음 
    auto_reply_service = AutoReplyService(db=db)
    outbox = GmailOutboxService(
        db=db,
        auto_reply_service=auto_reply_service,
        gmail_service=gmail_service,
    )

    items: List[AutoReplyJobItem] = []
    total_sent = 0
    total_target_messages = 0
    total_skipped_already_sent = 0
    total_skipped_no_message = 0

    # ------------------------------------------------------------------
    # 4) 파싱된 Gmail 메시지 기준으로 AutoReply 실행
    # ------------------------------------------------------------------
    for parsed in parsed_messages:
        gmail_message_id = parsed.id
        msg = msg_repo.get_by_gmail_message_id(gmail_message_id)

        if msg is None:
            # 이론상 거의 없겠지만, 방어적으로 처리
            total_skipped_no_message += 1
            items.append(
                AutoReplyJobItem(
                    gmail_message_id=gmail_message_id,
                    incoming_message_id=None,
                    sent=False,
                    skipped=True,
                    skip_reason="incoming_message not found after ingestion",
                )
            )
            continue

        # 이미 AutoReplyLog.sent=True 인 경우는 기본적으로 재전송하지 않음
        if not force and outbox._has_already_sent(msg.id):
            total_skipped_already_sent += 1
            items.append(
                AutoReplyJobItem(
                    gmail_message_id=gmail_message_id,
                    incoming_message_id=msg.id,
                    sent=False,
                    skipped=True,
                    skip_reason="already_sent",
                )
            )
            continue

        # 여기까지 왔으면 실제로 AutoReply를 시도할 대상
        total_target_messages += 1

        suggestion = outbox.send_auto_reply_for_message(
            message_id=msg.id,
            force=force,
        )

        # send_auto_reply_for_message 내부에서:
        #   - AutoReplyService 로 답변 생성
        #   - GmailSendAdapter 로 실제 발송
        #   - auto_reply_logs 에 log insert + commit
        # 이 모든 것이 끝난 뒤, 다시 sent 여부를 체크한다.
        sent_after = outbox._has_already_sent(msg.id)
        if sent_after:
            total_sent += 1

        items.append(
            AutoReplyJobItem(
                gmail_message_id=gmail_message_id,
                incoming_message_id=msg.id,
                sent=bool(sent_after),
                skipped=False,
                skip_reason=None,
            )
        )

    return AutoReplyJobResult(
        total_parsed=total_parsed,
        total_ingested=total_parsed,  # ingestion은 idempotent라, 실제 신규/기존 여부는 중요치 않으므로 전체 수로 보고
        total_target_messages=total_target_messages,
        total_sent=total_sent,
        total_skipped_already_sent=total_skipped_already_sent,
        total_skipped_no_message=total_skipped_no_message,
        items=items,
    )
