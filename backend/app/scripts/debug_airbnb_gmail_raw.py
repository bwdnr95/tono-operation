# backend/app/scripts/debug_airbnb_gmail_raw.py

from __future__ import annotations

import base64
import re
from typing import Any

from googleapiclient.discovery import Resource

from app.db.session import SessionLocal
from app.services.google_oauth_service import get_gmail_service
from app.adapters.gmail_utils import decode_mime_words


LISTING_ID_REGEX = re.compile(r"airbnb\.co(m|\.kr)/rooms/(\d+)", re.IGNORECASE)


def extract_first_text_or_html(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Gmail API message['payload'] 에서 text/plain, text/html 하나씩만 대충 뽑아서 디코딩.
    디버그용이니까 대충 가장 첫 파트만 보는 걸로 충분.
    """
    text_body = None
    html_body = None

    def decode_body(data: str | None) -> str | None:
        if not data:
            return None
        try:
            decoded_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))
            return decoded_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return None

    mime_type = payload.get("mimeType")
    body = payload.get("body", {}) or {}
    data = body.get("data")

    parts = payload.get("parts")

    # 단일 파트
    if not parts and data:
        decoded = decode_body(data)
        if mime_type == "text/plain":
            text_body = decoded
        elif mime_type == "text/html":
            html_body = decoded
        return text_body, html_body

    # 멀티파트
    for part in parts or []:
        p_mime = part.get("mimeType")
        p_data = (part.get("body") or {}).get("data")
        decoded = decode_body(p_data)

        if not decoded:
            continue

        if p_mime == "text/plain" and text_body is None:
            text_body = decoded
        elif p_mime == "text/html" and html_body is None:
            html_body = decoded

        if text_body and html_body:
            break

    return text_body, html_body


def debug_print_recent_airbnb_messages(max_results: int = 3) -> None:
    """
    최근 Airbnb 메일 몇 개를 가져와서
    - Subject
    - snippet
    - text/html 일부
    - rooms/{숫자} 패턴 있는지

    를 콘솔에 찍어준다.
    """
    db = SessionLocal()
    gmail: Resource = get_gmail_service(db)

    # Airbnb 관련 메일만 필터 (필요하면 q 수정 가능)
    result = (
        gmail.users()
        .messages()
        .list(
            userId="me",
            q="from:(airbnb.com) OR from:(@airbnb.com)",
            maxResults=max_results,
        )
        .execute()
    )

    messages_meta = result.get("messages", []) or []
    print(f"[DEBUG] Found {len(messages_meta)} Airbnb messages")

    for i, meta in enumerate(messages_meta, start=1):
        msg = (
            gmail.users()
            .messages()
            .get(userId="me", id=meta["id"], format="full")
            .execute()
        )

        payload = msg.get("payload", {}) or {}
        headers = payload.get("headers", []) or []

        subject = ""
        from_email = ""

        for h in headers:
            name = h.get("name", "").lower()
            value = h.get("value", "")
            if name == "subject":
                subject = decode_mime_words(value)
            elif name == "from":
                from_email = value

        snippet = msg.get("snippet", "")

        text_body, html_body = extract_first_text_or_html(payload)

        print("\n" + "=" * 80)
        print(f"[{i}] gmail_message_id: {msg.get('id')}")
        print(f"    from:    {from_email}")
        print(f"    subject: {subject}")
        print(f"    snippet: {snippet}")
        print("-" * 80)

        # 본문 일부만 잘라서 보여주기 (너무 길면 힘드니까)
        if text_body:
            print("[text_body preview]")
            print(text_body[:800])
        elif html_body:
            print("[html_body preview]")
            print(html_body[:800])
        else:
            print("[no text/html body decoded]")

        # rooms/{숫자} 패턴 찾기
        merged = (text_body or "") + "\n" + (html_body or "")
        matches = LISTING_ID_REGEX.findall(merged)
        ids = re.findall(r"airbnb\.co(?:m|\.kr)/rooms/(\d+)", merged, flags=re.IGNORECASE)

        if ids:
            print(f"[LISTING_ID DETECTED] rooms/ IDs: {ids}")
        else:
            print("[LISTING_ID NOT FOUND] airbnb.com/rooms/{id} 패턴이 안 보입니다.")

        print("=" * 80)


if __name__ == "__main__":
    debug_print_recent_airbnb_messages(max_results=3)
