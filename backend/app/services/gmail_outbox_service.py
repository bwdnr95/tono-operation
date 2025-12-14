from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from googleapiclient.discovery import Resource
from sqlalchemy.orm import Session

from app.core.config import settings
from app.adapters.gmail_send_adapter import GmailSendAdapter
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.auto_reply_log import AutoReplyLog
from app.repositories.messages import IncomingMessageRepository
from app.services.auto_reply_service import AutoReplyService, AutoReplySuggestion
from app.domain.intents import MessageIntent, FineGrainedIntent
from app.domain.intents.auto_action import MessageActionType


@dataclass
class GmailOutboxService:
    """
    1) IncomingMessage 조회
    2) AutoReplyService로 답변 생성
    3) Gmail API로 실제 답장 전송
       - incoming_messages.gmail_message_id + thread_id 를 이용해
         Gmail에서 Reply-To 헤더를 재조회하여 게스트에게 전달될 주소로 보냄
    4) auto_reply_logs 에 전송 결과 기록
    """

    db: Session
    auto_reply_service: AutoReplyService
    gmail_service: Resource

    def __post_init__(self) -> None:
        print("[DEBUG][GmailOutboxService] __post_init__ 시작")
        self._msg_repo = IncomingMessageRepository(self.db)
        self._gmail = GmailSendAdapter(
            service=self.gmail_service,
            user_id="me",
            from_address=settings.GMAIL_USER,
        )
        print("[DEBUG][GmailOutboxService] __post_init__ 완료")

    def _has_already_sent(self, message_id: int) -> bool:
        """
        해당 message_id에 대해 이미 sent=True 인 로그가 있는지 확인.
        """
        print(f"[DEBUG][GmailOutboxService] _has_already_sent: message_id={message_id}")
        q = (
            self.db.query(AutoReplyLog)
            .filter(
                AutoReplyLog.message_id == message_id,
                AutoReplyLog.sent.is_(True),
            )
            .order_by(AutoReplyLog.id.desc())
        )
        exists = self.db.query(q.exists()).scalar()
        print(
            f"[DEBUG][GmailOutboxService] _has_already_sent 결과: {exists} "
            f"(message_id={message_id})"
        )
        return exists

    def _get_reply_target_from_gmail(self, msg: IncomingMessage) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Gmail API를 통해 원본 메시지의 헤더를 다시 조회하여
        Reply-To / From / To 를 가져온다.

        :return: (reply_to, from_addr, to_addr)
        """
        print(
            f"[DEBUG][GmailOutboxService] _get_reply_target_from_gmail 시작: "
            f"gmail_message_id={msg.gmail_message_id}"
        )

        gmail_msg = (
            self.gmail_service.users()
            .messages()
            .get(
                userId="me",
                id=msg.gmail_message_id,
                format="metadata",
                metadataHeaders=["Reply-To", "From", "To"],
            )
            .execute()
        )

        headers = gmail_msg.get("payload", {}).get("headers", [])
        reply_to = None
        from_addr = None
        to_addr = None

        for h in headers:
            name = h.get("name", "").lower()
            value = h.get("value", "")
            if name == "reply-to":
                reply_to = value
            elif name == "from":
                from_addr = value
            elif name == "to":
                to_addr = value

        print(
            "[DEBUG][GmailOutboxService] _get_reply_target_from_gmail 결과: "
            f"reply_to={reply_to}, from={from_addr}, to={to_addr}"
        )
        return reply_to, from_addr, to_addr

    def send_auto_reply_for_message(
        self,
        *,
        message_id: int,
        force: bool = False,
        override_reply_text: Optional[str] = None,
    ) -> Optional[AutoReplySuggestion]:
        """
        단일 incoming_message에 대해:
        - AutoReplySuggestion 생성
        - 조건 만족 시 Gmail로 실제 전송
        - auto_reply_logs 에 기록
        """
        print(
            f"[DEBUG][GmailOutboxService] send_auto_reply_for_message 시작: "
            f"message_id={message_id}, force={force}"
        )

        msg: IncomingMessage | None = self._msg_repo.get(message_id)
        print("[DEBUG][GmailOutboxService] 조회된 IncomingMessage:", msg)

        if msg is None:
            raise ValueError(f"IncomingMessage(id={message_id}) not found")

        # 이미 보낸 적 있으면 스킵 (force가 아니면)
        if not force and self._has_already_sent(message_id):
            print(
                f"[DEBUG][GmailOutboxService] 이미 sent=True 로그 존재 → 스킵: "
                f"message_id={message_id}"
            )
            return None

        print("[DEBUG][GmailOutboxService] AutoReplyService 호출 준비")

        # AutoReplyService는 async 이므로 sync로 감싼다.
        suggestion: Optional[AutoReplySuggestion] = asyncio.run(
            self.auto_reply_service.suggest_reply_for_message(
                message_id=message_id,
                ota=msg.ota or "airbnb",
                locale="ko",
                property_code=msg.property_code,
                use_llm=True,
            )
        )
        print(
            "[DEBUG][GmailOutboxService] AutoReplyService 결과 suggestion:",
            suggestion,
        )

        if suggestion is None:
            print(
                "[DEBUG][GmailOutboxService] suggestion이 None → 더 이상 진행하지 않음"
            )
            return None
        
        # 2) 프론트에서 override_reply_text가 들어오면, 그걸로 덮어쓰기
        if override_reply_text:
            # AutoReplySuggestion 이 pydantic 모델이라면:
            suggestion.reply_text = override_reply_text
            # generation_mode 같은 필드가 있다면, 타입에 맞게 상태도 바꿔주면 좋음
            # 예) suggestion.generation_mode = AutoReplyGenerationMode.MANUAL_OVERRIDE

        # 실제 전송 여부 결정
        should_send = (
            suggestion.allow_auto_send
            and suggestion.action == MessageActionType.AUTO_REPLY
        )
        print(
            f"[DEBUG][GmailOutboxService] should_send 초기값: {should_send}, "
            f"allow_auto_send={suggestion.allow_auto_send}, action={suggestion.action}"
        )

        if force:
            should_send = True
            print(
                "[DEBUG][GmailOutboxService] force=True 이므로 should_send 강제 True"
            )

        # AutoReplyLog용 intent 문자열 변환
        def _intent_to_str(v) -> Optional[str]:
            if v is None:
                return None
            if isinstance(v, (MessageIntent, FineGrainedIntent, MessageActionType)):
                return v.name
            return str(v)

        failure_reason: Optional[str] = None

        print(
            f"[DEBUG][GmailOutboxService] msg.thread_id={msg.thread_id}, "
            f"gmail_message_id={msg.gmail_message_id}"
        )

        can_send = should_send and bool(getattr(msg, "thread_id", None))
        print(
            f"[DEBUG][GmailOutboxService] can_send={can_send} "
            f"(should_send={should_send})"
        )

        sent_flag = False
        sent_at = None

        if can_send:
            # 🔥 여기서 Gmail 원본에서 Reply-To 를 다시 가져와서 사용
            reply_to, from_addr, to_addr = self._get_reply_target_from_gmail(msg)
            target_email = reply_to or from_addr or to_addr

            if target_email:
                print(
                    f"[DEBUG][GmailOutboxService] GmailSendAdapter.send_reply 호출: "
                    f"to={target_email}"
                )
                self._gmail.send_reply(
                    thread_id=msg.thread_id,
                    to_email=target_email,
                    subject=msg.subject or "",
                    reply_text=suggestion.reply_text,
                    original_message_id=msg.gmail_message_id,
                )
                sent_flag = True
                sent_at = datetime.now(timezone.utc)
                print("[DEBUG][GmailOutboxService] Gmail 전송 완료")
            else:
                failure_reason = (
                    "Cannot determine target email (no Reply-To/From/To headers)"
                )
                print(
                    "[DEBUG][GmailOutboxService] 전송 불가, failure_reason:",
                    failure_reason,
                )
        else:
            if should_send:
                failure_reason = (
                    f"Cannot send: thread_id={msg.thread_id} (should_send=True)"
                )
                print(
                    "[DEBUG][GmailOutboxService] 전송 불가, failure_reason:",
                    failure_reason,
                )
            else:
                print(
                    "[DEBUG][GmailOutboxService] should_send=False → Gmail 전송 생략"
                )

        # 로그 적재
        print("[DEBUG][GmailOutboxService] AutoReplyLog insert 준비")
        log = AutoReplyLog(
            message_id=message_id,
            property_code=msg.property_code,
            ota=msg.ota,
            intent=_intent_to_str(suggestion.intent),
            fine_intent=_intent_to_str(suggestion.fine_intent),
            intent_confidence=suggestion.intent_confidence,
            generation_mode=suggestion.generation_mode,
            template_id=suggestion.template_id,
            reply_text=suggestion.reply_text,
            send_mode="AUTOPILOT",
            sent=sent_flag,
            sent_at=sent_at,
            allow_auto_send=suggestion.allow_auto_send,
            failure_reason=failure_reason,
        )
        self.db.add(log)
        self.db.commit()
        print("[DEBUG][GmailOutboxService] AutoReplyLog insert & commit 완료")

        return suggestion