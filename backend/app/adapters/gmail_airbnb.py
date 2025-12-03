# backend/app/adapters/gmail_airbnb.py
from __future__ import annotations

import base64
import re
from email.message import Message
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.adapters.gmail_utils import decode_mime_words
from app.domain.models.incoming_message import IncomingMessage
from app.repositories.ota_listing_mapping_repository import OtaListingMappingRepository


class AirbnbEmailParser:
    """
    Airbnb 알림 이메일 전용 파서.

    기능:
      - raw Gmail message → subject/text/html/body 파싱
      - listing_id / listing_name 추출
      - ota='airbnb' 로 설정
      - listing_id 기반 property_code 자동 매핑
    """

    LISTING_ID_REGEX = re.compile(r"airbnb\.co(m|\.kr)/rooms/(\d+)", re.IGNORECASE)

    LISTING_NAME_PATTERNS = [
        re.compile(r'inquiry for\s+“(.+?)”', re.IGNORECASE),
        re.compile(r'inquiry for\s+"(.+?)"', re.IGNORECASE),
        re.compile(r'regarding\s+(.+)', re.IGNORECASE),
    ]

    @staticmethod
    def decode_body(message: Message) -> Tuple[str | None, str | None]:
        """
        Gmail payload.message → (text_body, html_body)
        """
        text_body = None
        html_body = None

        if message.is_multipart():
            for part in message.walk():
                ctype = part.get_content_type()
                try:
                    payload = part.get_payload(decode=True)
                except Exception:
                    payload = None
                if payload is None:
                    continue
                decoded = None
                try:
                    decoded = payload.decode(part.get_content_charset() or "utf-8")
                except Exception:
                    try:
                        decoded = payload.decode("utf-8", errors="ignore")
                    except Exception:
                        continue

                if ctype == "text/plain":
                    text_body = decoded
                elif ctype == "text/html":
                    html_body = decoded
        else:
            payload = message.get_payload(decode=True)
            try:
                text_body = payload.decode(message.get_content_charset() or "utf-8")
            except Exception:
                text_body = None

        return text_body, html_body

    # -------------------------------------------------------------

    def extract_listing_id(
        self, *, text: str | None, html: str | None
    ) -> Optional[str]:
        """
        Airbnb 메일에서 listing_id (숫자) 추출.
        """
        merged = (text or "") + "\n" + (html or "")
        m = self.LISTING_ID_REGEX.search(merged)
        if m:
            return m.group(2)
        return None

    def extract_listing_name(
        self, *, subject: str | None, text: str | None, html: str | None
    ) -> Optional[str]:
        """
        다양한 Airbnb 템플릿에서 숙소명 추출.
        """
        candidates = [subject or "", text or "", html or ""]
        for body in candidates:
            for pattern in self.LISTING_NAME_PATTERNS:
                m = pattern.search(body)
                if m:
                    return m.group(1).strip()
        return None

    # -------------------------------------------------------------

    def parse_airbnb_message(
        self,
        *,
        gmail_msg_obj: Message,
        session: Session,
    ) -> IncomingMessage:
        """
        Gmail Message → IncomingMessage 엔티티 생성.

        listing_id 기반으로 property_code 자동 매핑까지 처리.
        """

        subject = decode_mime_words(gmail_msg_obj.get("Subject", ""))
        from_email = gmail_msg_obj.get("From")

        text_body, html_body = self.decode_body(gmail_msg_obj)

        # 1) Listing 정보 추출
        listing_id = self.extract_listing_id(text=text_body, html=html_body)
        listing_name = self.extract_listing_name(
            subject=subject, text=text_body, html=html_body
        )

        # 2) 기존 매핑 테이블에서 property_code 조회
        property_code = None
        if listing_id:
            mapping_repo = OtaListingMappingRepository(session)
            mapping = mapping_repo.get_by_ota_and_listing_id(
                ota="airbnb",
                listing_id=listing_id,
                active_only=True,
            )
            if mapping:
                property_code = mapping.property_code

        # 3) IncomingMessage 생성
        im = IncomingMessage(
            gmail_message_id=gmail_msg_obj["id"],
            thread_id=gmail_msg_obj["threadId"],
            subject=subject,
            from_email=from_email,
            received_at=None,  # Gmail fetch 시점에서 채움
            text_body=text_body,
            html_body=html_body,
            pure_guest_message=None,  # 이후 전처리 단계에서 채움

            # OTA 메타
            ota="airbnb",
            ota_listing_id=listing_id,
            ota_listing_name=listing_name,

            # property 자동 매핑 결과
            property_code=property_code,
        )

        return im
