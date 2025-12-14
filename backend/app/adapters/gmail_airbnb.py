from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, date
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple, List

from googleapiclient.discovery import Resource
from sqlalchemy.orm import Session

from app.services.gmail_fetch_service import get_gmail_service
from app.repositories.ota_listing_mapping_repository import (
    OtaListingMappingRepository,
)


# -------------------------------------------------------------------
# 유틸 함수들
# -------------------------------------------------------------------


def _decode_header_value(value: str | None) -> str:
    """
    MIME 인코딩 된 Subject 등을 사람이 읽을 수 있는 문자열로 디코딩.
    """
    if not value:
        return ""
    try:
        parts = decode_header(value)
        decoded = ""
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded += part.decode(enc or "utf-8", errors="ignore")
            else:
                decoded += part
        return decoded
    except Exception:
        return value or ""


def _decode_body_part(part: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Gmail message payload 의 단일 part 에서 text/plain, text/html 디코딩.
    """
    mime = part.get("mimeType")
    data = part.get("body", {}).get("data")

    if not data:
        return None, None

    try:
        decoded_bytes = base64.urlsafe_b64decode(data)
    except Exception:
        return None, None

    try:
        text = decoded_bytes.decode("utf-8", errors="ignore")
    except Exception:
        text = None

    if mime == "text/plain":
        return text, None
    if mime == "text/html":
        return None, text
    return None, None


def _extract_bodies(payload: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Gmail payload 전체에서 text/plain, text/html 을 찾아서 합쳐준다.
    """
    mime = payload.get("mimeType", "")
    text_body: Optional[str] = None
    html_body: Optional[str] = None

    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            t, h = _extract_bodies(part)
            if t:
                text_body = (text_body or "") + t
            if h:
                html_body = (html_body or "") + h
    else:
        t, h = _decode_body_part(payload)
        if t:
            text_body = (text_body or "") + t
        if h:
            html_body = (html_body or "") + h

    return text_body, html_body


def _parse_gmail_date(date_str: str | None) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt
    except Exception:
        return None


# -------------------------------------------------------------------
# Airbnb 메타 추출 (listing_id, listing_name, property_code)
# -------------------------------------------------------------------


LISTING_ID_REGEX = re.compile(r"airbnb\.co(m|\.kr)/rooms/(\d+)", re.IGNORECASE)

LISTING_NAME_PATTERNS_EN = [
    re.compile(r'inquiry for\s+“(.+?)”', re.IGNORECASE),
    re.compile(r'inquiry for\s+"(.+?)"', re.IGNORECASE),
    re.compile(r'regarding\s+(.+)', re.IGNORECASE),
]

# 한국어 [오픈특가]제주에서 만나는 ... B
LISTING_NAME_PATTERN_KR_BRACKET = re.compile(
    r"\[[^\]]+\][^\n]+", re.MULTILINE
)


def _extract_listing_id(
    text: str | None,
    html: str | None,
    subject: str | None,
) -> Optional[str]:
    merged = (subject or "") + "\n" + (text or "") + "\n" + (html or "")
    m = LISTING_ID_REGEX.search(merged)
    if m:
        return m.group(2)
    return None


def _extract_listing_name(
    subject: str | None,
    text: str | None,
    html: str | None,
) -> Optional[str]:
    """
    다양한 Airbnb 템플릿에서 숙소명 추출.
    - 영어 inquiry 메일
    - 한국어 [오픈특가] 템플릿
    """
    # 1) 영어 템플릿
    candidates = [subject or "", text or "", html or ""]
    for body in candidates:
        for pattern in LISTING_NAME_PATTERNS_EN:
            m = pattern.search(body)
            if m:
                return m.group(1).strip()

    # 2) 한국어: [오픈특가] ... 한 줄 전체
    merged = (text or "") + "\n" + (subject or "")
    m = LISTING_NAME_PATTERN_KR_BRACKET.search(merged)
    if m:
        return m.group(0).strip()

    return None


# -------------------------------------------------------------------
# 게스트 이름 / 숙박일(체크인/체크아웃) 추출
# -------------------------------------------------------------------


# From 헤더에서 게스트 이름 추출: "홍길동 via Airbnb <xxx@airbnb.com>"
FROM_NAME_REGEX = re.compile(r'^"?(.+?)"?\s*<', re.UNICODE)

# 숫자형 날짜: 2025-12-08, 2025.12.08, 2025/12/08
DATE_NUMERIC_REGEX = re.compile(
    r"(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})"
)

# 한글 날짜: 2025년 12월 8일
DATE_KR_FULL_REGEX = re.compile(
    r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"
)

# 제목/숙소명 옆에 나오는 범위: (12월 8일~9일) / 12월 8일~9일
DATE_KR_RANGE_SUBJECT_REGEX = re.compile(
    r"\(?\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*[~\-]\s*(\d{1,2})\s*일\s*\)?"
)


def _extract_guest_name_from_from_header(from_addr: str | None) -> Optional[str]:
    if not from_addr:
        return None

    m = FROM_NAME_REGEX.search(from_addr)
    if not m:
        return None

    name = m.group(1).strip()
    # "홍길동 via Airbnb" → "홍길동"
    if "via Airbnb" in name:
        name = name.split("via Airbnb", 1)[0].strip()

    lower_name = name.lower()
    # "Airbnb", "Airbnb Messaging" 같은 시스템 메일은 제외
    if "airbnb" in lower_name:
        return None

    return name or None


def _extract_guest_name(
    from_addr: str | None,
    subject: str | None,
    text: str | None,
    html: str | None,
) -> Optional[str]:
    """
    게스트 이름 추출 규칙:

      1) text/html 본문에서 '예약자' 블록 찾기 (예: '유주\n\n예약자')
      2) 그래도 못 찾으면 None (From 헤더는 더 이상 사용하지 않음)

    Airbnb 메일 특성상 From 은 거의 항상 "에어비앤비" 이므로,
    From 기반 게스트 이름 추출은 프로젝트 요구사항에 맞지 않는다.
    """
    base_text = (text or "") + "\n" + (html or "")

    # 1) "[이름]\\n예약자" 패턴
    m = re.search(r"\n\s*([^\n]+?)\s*\n\s*예약자", base_text)
    if m:
        candidate = m.group(1).strip()
        if candidate and "airbnb" not in candidate.lower() and "에어비앤비" not in candidate:
            return candidate

    # 2) "이름 예약자" 패턴
    m = re.search(
        r"([A-Za-z가-힣][A-Za-z가-힣\s]{0,20})\s*예약자",
        base_text,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate and "airbnb" not in candidate.lower() and "에어비앤비" not in candidate:
            return candidate

    # 3) "예약자: 이름" 패턴
    m = re.search(
        r"예약자\s*[:,]?\s*([A-Za-z가-힣][A-Za-z가-힣\s]{0,20})",
        base_text,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate and "airbnb" not in candidate.lower() and "에어비앤비" not in candidate:
            return candidate

    # ❌ From 헤더는 이제 게스트 이름으로 사용하지 않는다.
    #    게스트 이름을 못 찾으면 그냥 None.
    return None


def _parse_date_ymd(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except Exception:
        return None


def _find_date_after_keyword(
    text: str,
    keywords: list[str],
) -> Optional[date]:
    """
    'Check-in', '체크인' 같은 키워드가 포함된 줄에서 날짜 패턴을 찾는다.
    - YYYY-MM-DD / YYYY.MM.DD / YYYY/MM/DD
    - YYYY년 M월 D일
    """
    lines = text.splitlines()
    for line in lines:
        if not any(k in line for k in keywords):
            continue

        # 숫자 포맷
        m = DATE_NUMERIC_REGEX.search(line)
        if m:
            return _parse_date_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        # 한글 포맷
        m2 = DATE_KR_FULL_REGEX.search(line)
        if m2:
            return _parse_date_ymd(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))

    return None


def _extract_stay_dates_from_body(
    text: str | None,
    html: str | None,
) -> Tuple[Optional[date], Optional[date]]:
    """
    Airbnb 메일 본문에서 체크인/체크아웃 날짜를 추출.
    """
    base = (text or "")  # 일단 text 위주로 탐색

    checkin = _find_date_after_keyword(
        base,
        ["Check-in", "Check In", "체크인", "입실"],
    )
    checkout = _find_date_after_keyword(
        base,
        ["Check-out", "Check Out", "체크아웃", "퇴실"],
    )

    return checkin, checkout


def _extract_stay_dates_from_subject_range(
    subject: str | None,
    received_at: Optional[datetime],
) -> Tuple[Optional[date], Optional[date]]:
    """
    제목/숙소명에 있는 "(12월 8일~9일)" 같은 패턴에서 날짜 범위 추출.
    연도는:
      - 우선 received_at.year 사용
      - 없으면 올해 기준
    """
    if not subject:
        return None, None

    m = DATE_KR_RANGE_SUBJECT_REGEX.search(subject)
    if not m:
        return None, None

    month = int(m.group(1))
    day_start = int(m.group(2))
    day_end = int(m.group(3))

    base_year = (received_at.year if received_at else datetime.utcnow().year)

    checkin = _parse_date_ymd(base_year, month, day_start)
    checkout = _parse_date_ymd(base_year, month, day_end)

    # 만약 종료일이 시작일보다 작으면 (예: 12월 30일~1월 2일 같은 케이스를 단순 처리)
    # 지금은 복잡하게 안 가고, 종료일 < 시작일이면 "한 달 뒤" 정도로만 처리
    if checkin and checkout and checkout < checkin:
        # month + 1 / year 보정
        next_month = month + 1
        next_year = base_year
        if next_month > 12:
            next_month = 1
            next_year += 1
        checkout = _parse_date_ymd(next_year, next_month, day_end)

    return checkin, checkout


def _extract_stay_dates(
    text: str | None,
    html: str | None,
    subject: str | None,
    received_at: Optional[datetime],
) -> Tuple[Optional[date], Optional[date]]:
    """
    최종 체크인/체크아웃 추출:
      1) 본문에서 키워드 기반 날짜 파싱
      2) 실패하면 제목에서 "(12월 8일~9일)" 패턴 찾기
    """
    checkin, checkout = _extract_stay_dates_from_body(text, html)

    if not checkin or not checkout:
        alt_checkin, alt_checkout = _extract_stay_dates_from_subject_range(
            subject=subject,
            received_at=received_at,
        )
        if not checkin:
            checkin = alt_checkin
        if not checkout:
            checkout = alt_checkout

    return checkin, checkout


# -------------------------------------------------------------------
# ParsedInternalMessage: ingestion 단계에서 사용하는 내부 DTO
# -------------------------------------------------------------------


@dataclass
class ParsedInternalMessage:
    id: str
    thread_id: str
    from_email: Optional[str]
    subject: Optional[str]
    decoded_text_body: Optional[str]
    decoded_html_body: Optional[str]
    received_at: Optional[datetime]
    snippet: Optional[str]

    ota: Optional[str] = "airbnb"
    ota_listing_id: Optional[str] = None
    ota_listing_name: Optional[str] = None
    property_code: Optional[str] = None

    # 🔹 TONO 확장 메타
    guest_name: Optional[str] = None
    checkin_date: Optional[date] = None
    checkout_date: Optional[date] = None


# -------------------------------------------------------------------
# Gmail API 호출 + Airbnb 메일 파싱
# -------------------------------------------------------------------


def _parse_single_message(msg: dict, db: Session) -> ParsedInternalMessage:
    gmail_message_id = msg.get("id")
    gmail_thread_id = msg.get("threadId")
    snippet = msg.get("snippet")

    payload = msg.get("payload", {}) or {}
    headers = payload.get("headers", []) or []

    def _get_header(name: str) -> Optional[str]:
        for h in headers:
            if h.get("name") == name:
                return h.get("value")
        return None

    raw_subject = _get_header("Subject") or ""
    subject = _decode_header_value(raw_subject)
    from_addr = _get_header("From") or ""
    date_str = _get_header("Date")

    received_at = _parse_gmail_date(date_str)

    text_body, html_body = _extract_bodies(payload)

    # Airbnb 메타 추출
    listing_id = _extract_listing_id(text_body, html_body, subject)
    listing_name = _extract_listing_name(subject, text_body, html_body)

    property_code = None
    if listing_id:
        mapping_repo = OtaListingMappingRepository(db)
        mapping = mapping_repo.get_by_ota_and_listing_id(
            ota="airbnb",
            listing_id=listing_id,
            active_only=True,
        )
        if mapping:
            property_code = mapping.property_code

    # 🔹 게스트 이름 / 체크인/체크아웃 추출
    guest_name = _extract_guest_name(
        from_addr=from_addr,
        subject=subject,
        text=text_body,
        html=html_body,
    )
    checkin_date, checkout_date = _extract_stay_dates(
        text=text_body,
        html=html_body,
        subject=subject,
        received_at=received_at,
    )

    return ParsedInternalMessage(
        id=gmail_message_id,
        thread_id=gmail_thread_id,
        from_email=from_addr,
        subject=subject,
        decoded_text_body=text_body,
        decoded_html_body=html_body,
        received_at=received_at,
        snippet=snippet,
        ota="airbnb",
        ota_listing_id=listing_id,
        ota_listing_name=listing_name,
        property_code=property_code,
        guest_name=guest_name,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
    )


def _build_search_query(
    *,
    newer_than_days: int = 3,
    extra_query: str | None = None,
) -> str:
    """
    기본 Airbnb 호스트 알림 메일 검색용 쿼리 생성.
    (기존 코드와 호환을 위해 남겨둠)
    """
    base = "from:airbnb.com"
    if newer_than_days > 0:
        base += f" newer_than:{newer_than_days}d"
    if extra_query:
        base += f" {extra_query}"
    return base


def fetch_and_parse_recent_airbnb_messages(
    *,
    db: Session,
    max_results: int = 50,
    newer_than_days: int = 3,
    extra_query: str | None = None,
    query: str | None = None,
    dry_run: bool = False,
) -> List[ParsedInternalMessage]:
    """
    Gmail API에서 Airbnb 관련 메일을 가져와 ParsedInternalMessage 리스트로 반환.
    기존 gmail_airbnb_ingest_service 는 이렇게 호출함:
        fetch_and_parse_recent_airbnb_messages(
            db=db,
            max_results=max_results,
            query=query,
        )
    """
    service: Resource = get_gmail_service(db)

    if query is None:
        query = _build_search_query(
            newer_than_days=newer_than_days,
            extra_query=extra_query,
        )

    print("[gmail_airbnb] Gmail 메시지 검색 중...")
    print(f"  query: {query}")
    print(f"  max_results: {max_results}")

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

    msg_metas = resp.get("messages", [])
    if not msg_metas:
        print("[gmail_airbnb] 검색 결과가 없습니다.")
        return []

    parsed_list: List[ParsedInternalMessage] = []

    for idx, meta in enumerate(msg_metas, start=1):
        msg_id = meta["id"]

        full_msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )

        parsed = _parse_single_message(full_msg, db=db)
        parsed_list.append(parsed)

        print("================================================================================")
        print(f"[{idx}] gmail_message_id: {parsed.id}")
        print(f"    from:    {parsed.from_email}")
        print(f"    subject: {parsed.subject}")
        print(f"    snippet: {parsed.snippet}")
        if parsed.ota_listing_id:
            print(
                f"[LISTING_ID DETECTED] rooms/ ID: {parsed.ota_listing_id} "
                f"(name: {parsed.ota_listing_name}, property_code={parsed.property_code})"
            )
        if parsed.guest_name:
            print(f"    guest_name: {parsed.guest_name}")
        if parsed.checkin_date or parsed.checkout_date:
            print(f"    stay: {parsed.checkin_date} ~ {parsed.checkout_date}")

        print("--------------------------------------------------------------------------------")
        if parsed.decoded_text_body:
            preview = parsed.decoded_text_body[:400].replace("\n", "\\n")
            print(f"[text_body preview]\n{preview}")
        print("================================================================================\n")

    print(f"[gmail_airbnb] 총 {len(parsed_list)}건의 Airbnb 메시지를 파싱했습니다.")
    return parsed_list
