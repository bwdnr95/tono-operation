# backend/app/adapters/gmail_send_adapter.py
from __future__ import annotations

import base64
from email.message import EmailMessage as StdEmailMessage
from typing import Optional

from googleapiclient.discovery import Resource


class GmailSendAdapter:
    """
    Gmail API를 통해 실제 이메일을 전송하는 어댑터.

    - token.json 같은 파일을 쓰지 않고,
      이미 DB에 저장된 토큰 기반으로 생성한 Gmail service(Resource)를 그대로 주입해서 사용한다.
    """

    def __init__(
        self,
        *,
        service: Resource,
        user_id: str = "me",
        from_address: Optional[str] = None,
    ) -> None:
        """
        :param service: googleapiclient.discovery.build("gmail","v1",...) 결과
        :param user_id: Gmail API userId ("me" 권장)
        :param from_address: From 헤더에 들어갈 이메일 주소
        """
        self._service = service
        self._user_id = user_id
        self._from_address = from_address

    def send_reply(
        self,
        *,
        gmail_thread_id: str,
        to_email: str,
        subject: str,
        reply_text: str,
        original_message_id: Optional[str] = None,
    ) -> dict:
        """
        Gmail 스레드에 답장을 전송한다.

        :param gmail_thread_id: Gmail API threadId
        :param to_email: 게스트 이메일 주소
        :param subject: 원본 메일 제목 (자동으로 "Re: " prefix 붙음)
        :param reply_text: 평문 본문
        :param original_message_id: Gmail 메시지의 Message-ID (있으면 In-Reply-To/References에 사용)
        :return: Gmail API 응답 JSON
        """
        msg = StdEmailMessage()

        msg["To"] = to_email

        if subject.lower().startswith("re:"):
            msg["Subject"] = subject
        else:
            msg["Subject"] = f"Re: {subject}"

        if self._from_address:
            msg["From"] = self._from_address

        if original_message_id:
            # RFC 5322 스레딩용 헤더
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id

        msg.set_content(reply_text)

        raw_bytes = msg.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

        body = {
            "raw": raw_b64,
            "threadId": gmail_thread_id,
        }

        return (
            self._service.users()
            .messages()
            .send(userId=self._user_id, body=body)
            .execute()
        )
