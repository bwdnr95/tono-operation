# backend/app/adapters/gmail_utils.py

from __future__ import annotations

from email.header import decode_header
from typing import Optional


def decode_mime_words(raw: Optional[str]) -> Optional[str]:
    """
    Gmail 제목/이름 등에 포함되는 MIME 인코딩 문자열을 UTF-8 문자열로 디코딩한다.

    예:
      "=?UTF-8?B?7JWI64WV7ZWY?=" → "문의드립니다"

    decode_header 가 반환하는 튜플 리스트를 안전하게 병합해 UTF-8 str 로 변환한다.
    """
    if raw is None:
        return None

    decoded_parts = decode_header(raw)
    result = ""

    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                result += part.decode(encoding or "utf-8", errors="ignore")
            except Exception:
                result += part.decode("utf-8", errors="ignore")
        else:
            # already str
            result += part

    return result.strip()
