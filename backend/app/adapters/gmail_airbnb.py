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
# Airbnb 메타 추출 (listing_id, listing_name, property_code, airbnb_thread_id)
# -------------------------------------------------------------------

# Airbnb Thread ID 추출 (hosting/thread/숫자)
AIRBNB_THREAD_ID_REGEX = re.compile(r"/hosting/thread/(\d+)", re.IGNORECASE)

# Reservation Code 추출 (reservations/details/코드)
RESERVATION_CODE_REGEX = re.compile(r"/reservations/details/([A-Z0-9]+)", re.IGNORECASE)

# Alteration ID 추출 (alterations/숫자)
ALTERATION_ID_REGEX = re.compile(r"/alterations/(\d+)", re.IGNORECASE)


def _extract_airbnb_thread_id(
    text: str | None,
    html: str | None,
) -> Optional[str]:
    """
    이메일 본문에서 Airbnb Thread ID 추출.
    
    패턴: /hosting/thread/2335308720
    
    Returns:
        Airbnb Thread ID (예: "2335308720"), 없으면 None
    """
    merged = (text or "") + "\n" + (html or "")
    m = AIRBNB_THREAD_ID_REGEX.search(merged)
    if m:
        return m.group(1)
    return None


def _extract_reservation_code_from_url(
    text: str | None,
    html: str | None,
) -> Optional[str]:
    """
    이메일 본문에서 Reservation Code 추출 (URL 패턴).
    
    패턴: /reservations/details/HMB8RYSB8Y
    
    기존 _extract_reservation_code와 별개로, URL에서만 추출
    """
    merged = (text or "") + "\n" + (html or "")
    m = RESERVATION_CODE_REGEX.search(merged)
    if m:
        return m.group(1)
    return None


def _extract_alteration_id(
    text: str | None,
    html: str | None,
) -> Optional[str]:
    """
    이메일 본문에서 Alteration ID 추출.
    
    패턴: /alterations/1577166496855829540
    """
    merged = (text or "") + "\n" + (html or "")
    m = ALTERATION_ID_REGEX.search(merged)
    if m:
        return m.group(1)
    return None


@dataclass
class ParsedAlterationDates:
    """변경 요청 날짜 정보"""
    original_checkin: Optional[date] = None
    original_checkout: Optional[date] = None
    requested_checkin: Optional[date] = None
    requested_checkout: Optional[date] = None
    guest_name: Optional[str] = None
    listing_name: Optional[str] = None


def _parse_alteration_request_dates(
    text: str | None,
    html: str | None,
    received_at: Optional[datetime] = None,
) -> ParsedAlterationDates:
    """
    변경 요청 메일에서 기존/요청 날짜 파싱.
    
    패턴:
    기존 날짜
    2026년 1월 30일 - 1월 31일
    
    요청 날짜
    2026년 1월 23일 - 1월 24일
    """
    result = ParsedAlterationDates()
    base_text = (text or "") + "\n" + (html or "")
    
    # 연도 추정
    base_year = received_at.year if received_at else datetime.utcnow().year
    
    # 기존 날짜 패턴: "기존 날짜" 다음 줄
    # 2026년 1월 30일 - 1월 31일
    original_match = re.search(
        r"기존\s*날짜[^\n]*\n\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*[-–]\s*(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일",
        base_text
    )
    if original_match:
        year1 = int(original_match.group(1))
        month1 = int(original_match.group(2))
        day1 = int(original_match.group(3))
        year2 = int(original_match.group(4)) if original_match.group(4) else year1
        month2 = int(original_match.group(5))
        day2 = int(original_match.group(6))
        
        try:
            result.original_checkin = date(year1, month1, day1)
            result.original_checkout = date(year2, month2, day2)
        except ValueError:
            pass
    
    # 요청 날짜 패턴: "요청 날짜" 다음 줄
    requested_match = re.search(
        r"요청\s*날짜[^\n]*\n\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*[-–]\s*(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일",
        base_text
    )
    if requested_match:
        year1 = int(requested_match.group(1))
        month1 = int(requested_match.group(2))
        day1 = int(requested_match.group(3))
        year2 = int(requested_match.group(4)) if requested_match.group(4) else year1
        month2 = int(requested_match.group(5))
        day2 = int(requested_match.group(6))
        
        try:
            result.requested_checkin = date(year1, month1, day1)
            result.requested_checkout = date(year2, month2, day2)
        except ValueError:
            pass
    
    # 게스트 이름: 보통 변경 요청 메일에서 "건모님이 변경 요청" 같은 패턴
    guest_match = re.search(r"([가-힣A-Za-z]+)님이\s*(?:예약\s*)?변경", base_text)
    if guest_match:
        result.guest_name = guest_match.group(1)
    
    # 숙소명: [오픈특가]... 패턴
    listing_match = re.search(r"(\[[^\]]+\][^\n]{10,100})", base_text)
    if listing_match:
        result.listing_name = listing_match.group(1).strip()
    
    return result


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

# BOOKING_INITIAL_INQUIRY용: "12월 24일" 또는 "12월 24일 (수)" 패턴
DATE_KR_SHORT_REGEX = re.compile(
    r"(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\([월화수목금토일]\))?"
)


def _extract_guest_name_for_inquiry(
    subject: str | None,
    text: str | None,
    html: str | None,
) -> Optional[str]:
    """
    BOOKING_INITIAL_INQUIRY 전용 게스트 이름 추출.
    
    패턴:
    1. "승민님의 문의에 답하세요" → "승민"
    2. HTML에서 aria-label="승민" → "승민"
    3. 본문에서 이름 블록 찾기
    """
    base_text = (text or "") + "\n" + (html or "")
    
    # 1) "OOO님의 문의에 답하세요" 패턴 (subject 또는 본문)
    combined = (subject or "") + "\n" + base_text
    m = re.search(r"([가-힣A-Za-z]+)님의 문의에 답하세요", combined)
    if m:
        return m.group(1).strip()
    
    # 2) HTML aria-label에서 이름 추출
    # <a ... aria-label="승민" ...>
    m = re.search(r'aria-label="([가-힣A-Za-z]+)"', html or "")
    if m:
        candidate = m.group(1).strip()
        # 숙소명이나 시스템 문구 제외
        if len(candidate) <= 10 and "airbnb" not in candidate.lower():
            return candidate
    
    # 3) 본문에서 이름 + "본인 인증 완료" 패턴
    # 승민
    # 본인 인증 완료 · 후기 2개
    m = re.search(r"\n\s*([가-힣A-Za-z]+)\s*\n\s*본인 인증", base_text)
    if m:
        return m.group(1).strip()
    
    return None


def _extract_dates_for_inquiry(
    text: str | None,
    html: str | None,
    received_at: Optional[datetime] = None,
) -> Tuple[Optional[date], Optional[date]]:
    """
    BOOKING_INITIAL_INQUIRY 전용 체크인/체크아웃 추출.
    
    패턴:
    체크인           체크아웃
    12월 24일 (수)   12월 25일 (목)
    """
    base_text = (text or "") + "\n" + (html or "")
    
    checkin_date = None
    checkout_date = None
    
    # 연도 추정
    base_year = received_at.year if received_at else datetime.utcnow().year
    
    # 방법 1: "체크인" 키워드 근처에서 날짜 찾기
    lines = base_text.splitlines()
    
    for i, line in enumerate(lines):
        # 체크인/체크아웃이 같은 줄이나 인접한 줄에 있는 경우
        if "체크인" in line:
            # 같은 줄에서 날짜 찾기
            dates = DATE_KR_SHORT_REGEX.findall(line)
            if dates:
                checkin_date = _parse_date_ymd(base_year, int(dates[0][0]), int(dates[0][1]))
            
            # 다음 줄들에서 날짜 찾기
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j]
                dates = DATE_KR_SHORT_REGEX.findall(next_line)
                if dates and not checkin_date:
                    checkin_date = _parse_date_ymd(base_year, int(dates[0][0]), int(dates[0][1]))
                    break
        
        if "체크아웃" in line:
            # 같은 줄에서 날짜 찾기
            dates = DATE_KR_SHORT_REGEX.findall(line)
            if dates:
                checkout_date = _parse_date_ymd(base_year, int(dates[0][0]), int(dates[0][1]))
            
            # 다음 줄들에서 날짜 찾기
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j]
                dates = DATE_KR_SHORT_REGEX.findall(next_line)
                if dates and not checkout_date:
                    checkout_date = _parse_date_ymd(base_year, int(dates[0][0]), int(dates[0][1]))
                    break
    
    # 방법 2: HTML에서 구조화된 날짜 찾기
    # "12월 24일 (수)" 형식의 모든 날짜를 찾아서 순서대로 체크인/체크아웃
    if not checkin_date or not checkout_date:
        all_dates = DATE_KR_SHORT_REGEX.findall(base_text)
        if len(all_dates) >= 2:
            if not checkin_date:
                checkin_date = _parse_date_ymd(base_year, int(all_dates[0][0]), int(all_dates[0][1]))
            if not checkout_date:
                checkout_date = _parse_date_ymd(base_year, int(all_dates[1][0]), int(all_dates[1][1]))
    
    # 연도 보정: 체크인이 현재 월보다 이전이면 다음 해
    if checkin_date and received_at:
        if checkin_date.month < received_at.month:
            checkin_date = checkin_date.replace(year=base_year + 1)
        if checkout_date and checkout_date.month < received_at.month:
            checkout_date = checkout_date.replace(year=base_year + 1)
    
    return checkin_date, checkout_date


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

      0) 예약 확정 이메일: 유니코드 특수 문자 ⁨...⁩ (U+2068...U+2069) 패턴
      1) text/html 본문에서 '예약자' 블록 찾기 (예: '유주\n\n예약자')
      2) 그래도 못 찾으면 None (From 헤더는 더 이상 사용하지 않음)

    Airbnb 메일 특성상 From 은 거의 항상 "에어비앤비" 이므로,
    From 기반 게스트 이름 추출은 프로젝트 요구사항에 맞지 않는다.
    """
    base_text = (text or "") + "\n" + (html or "")
    subject_text = subject or ""
    
    # 0) 예약 확정 이메일용: 유니코드 특수 문자 ⁨...⁩ (U+2068...U+2069) 패턴
    #    Subject: "예약 확정 - ⁨Eric S.⁩ Hong 님이 12월 27일에 체크인할 예정입니다"
    #    본문: "⁨Eric S.⁩"
    unicode_pattern = r'\u2068([^\u2069]+)\u2069'
    
    # Subject에서 먼저 시도
    m = re.search(unicode_pattern, subject_text)
    if m:
        candidate = m.group(1).strip()
        if candidate and len(candidate) >= 2:
            return candidate
    
    # 본문에서 시도
    m = re.search(unicode_pattern, base_text)
    if m:
        candidate = m.group(1).strip()
        if candidate and len(candidate) >= 2:
            return candidate

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
    received_at: Optional[datetime] = None,
    is_checkout: bool = False,
) -> Optional[date]:
    """
    'Check-in', '체크인' 같은 키워드가 포함된 줄 또는 그 다음 줄에서 날짜 패턴을 찾는다.
    - YYYY-MM-DD / YYYY.MM.DD / YYYY/MM/DD
    - YYYY년 M월 D일
    - M월 D일 (연도 없음 - received_at 기준으로 추정)
    
    is_checkout=True일 때, 같은 줄에 체크인/체크아웃이 함께 있으면 두 번째 날짜를 반환
    """
    base_year = (received_at.year if received_at else datetime.utcnow().year)
    
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not any(k in line for k in keywords):
            continue

        # 체크인과 체크아웃이 같은 줄에 있는지 확인
        has_both = ("체크인" in line or "Check-in" in line or "Check In" in line) and \
                   ("체크아웃" in line or "Check-out" in line or "Check Out" in line)

        # 키워드가 있는 줄 + 다음 3줄까지 검색
        search_lines = [line] + [lines[j] for j in range(i + 1, min(i + 4, len(lines)))]
        
        for search_line in search_lines:
            # 숫자 포맷
            m = DATE_NUMERIC_REGEX.search(search_line)
            if m:
                return _parse_date_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))

            # 한글 풀 포맷 (연도 포함) - 여러 개 있을 수 있음
            matches_full = DATE_KR_FULL_REGEX.findall(search_line)
            if matches_full:
                if has_both and is_checkout and len(matches_full) >= 2:
                    # 체크아웃은 두 번째 날짜
                    y, m, d = matches_full[1]
                    return _parse_date_ymd(int(y), int(m), int(d))
                else:
                    y, m, d = matches_full[0]
                    return _parse_date_ymd(int(y), int(m), int(d))
            
            # 한글 짧은 포맷 (연도 없음): "12월 27일 (토)" - 여러 개 있을 수 있음
            matches_short = DATE_KR_SHORT_REGEX.findall(search_line)
            if matches_short:
                if has_both and is_checkout and len(matches_short) >= 2:
                    # 체크아웃은 두 번째 날짜
                    m, d = matches_short[1]
                    return _parse_date_ymd(base_year, int(m), int(d))
                else:
                    m, d = matches_short[0]
                    return _parse_date_ymd(base_year, int(m), int(d))

    return None


def _extract_stay_dates_from_body(
    text: str | None,
    html: str | None,
    received_at: Optional[datetime] = None,
) -> Tuple[Optional[date], Optional[date]]:
    """
    Airbnb 메일 본문에서 체크인/체크아웃 날짜를 추출.
    """
    base = (text or "")  # 일단 text 위주로 탐색

    checkin = _find_date_after_keyword(
        base,
        ["Check-in", "Check In", "체크인", "입실"],
        received_at=received_at,
        is_checkout=False,
    )
    checkout = _find_date_after_keyword(
        base,
        ["Check-out", "Check Out", "체크아웃", "퇴실"],
        received_at=received_at,
        is_checkout=True,
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
    checkin, checkout = _extract_stay_dates_from_body(text, html, received_at=received_at)

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
    id: str  # gmail_message_id (여러 메시지면 suffix 붙음: id_0, id_1, ...)
    gmail_thread_id: str
    from_email: Optional[str]
    subject: Optional[str]
    decoded_text_body: Optional[str]  # 해당 메시지의 본문만
    decoded_html_body: Optional[str]
    received_at: Optional[datetime]
    snippet: Optional[str]

    reply_to: Optional[str] = None  # Reply-To 헤더
    ota: Optional[str] = "airbnb"
    ota_listing_id: Optional[str] = None
    ota_listing_name: Optional[str] = None
    property_code: Optional[str] = None

    # 🔹 TONO 확장 메타
    guest_name: Optional[str] = None
    checkin_date: Optional[date] = None
    checkout_date: Optional[date] = None
    
    # 🔹 발신자 역할 (파싱 단계에서 결정)
    sender_role: Optional[str] = None  # "예약자", "게스트", "호스트", None
    
    # 🔹 이메일 타입 분류 (X-Template 기반)
    x_template: Optional[str] = None  # 원본 X-Template 헤더 값
    email_type: Optional[str] = None  # "system_booking_confirmation", "guest_message", "system_other"
    
    # 🔹 예약 정보 (시스템 메일 또는 게스트 메시지에서 파싱)
    guest_count: Optional[int] = None
    child_count: Optional[int] = None
    infant_count: Optional[int] = None
    pet_count: Optional[int] = None
    reservation_code: Optional[str] = None
    nights: Optional[int] = None
    total_price: Optional[int] = None
    host_payout: Optional[int] = None
    checkin_time: Optional[str] = None  # "16:00" 형식
    checkout_time: Optional[str] = None  # "11:00" 형식
    
    # 🔹 Airbnb Thread ID (gmail_thread_id와 별개)
    airbnb_thread_id: Optional[str] = None  # /hosting/thread/숫자에서 추출
    
    # 🔹 변경 요청 관련 (system_alteration_requested 타입일 때만 사용)
    alteration_id: Optional[str] = None
    original_checkin: Optional[date] = None
    original_checkout: Optional[date] = None
    requested_checkin: Optional[date] = None
    requested_checkout: Optional[date] = None


# -------------------------------------------------------------------
# 이메일 타입 분류 (X-Template 기반)
# -------------------------------------------------------------------

# 시스템 메일 템플릿 - 예약 확정 (reservation_info 저장)
BOOKING_CONFIRMATION_TEMPLATES = {
    "BOOKING_CONFIRMATION_TO_HOST",  # 예약 확정
}

# 시스템 메일 템플릿 - 취소 (reservation_info status → canceled)
CANCELLATION_TEMPLATES = {
    "CANCELLATIONS_RESERVATION_CANCELED_BY_GUEST_TO_HOST",  # 게스트 취소
    "RESERVATION_CANCELLED_BY_HOST",  # 호스트 취소
    "RESERVATION_CANCELLED_BY_GUEST",  # 게스트 취소 (다른 형식)
}

# 시스템 메일 템플릿 - 변경 수락 (alteration_request 처리 + reservation_info 날짜 업데이트)
ALTERATION_ACCEPTED_TEMPLATES = {
    "ALTERATION_ACCEPTED",  # 예약 변경 완료
}

# 시스템 메일 템플릿 - 변경 거절 (alteration_request 상태만 업데이트)
ALTERATION_DECLINED_TEMPLATES = {
    "ALTERATION_DECLINED",  # 예약 변경 거절
    "ALTERATION_DECLINED_BY_HOST",  # 호스트가 거절
    "ALTERATION_DECLINED_BY_GUEST",  # 게스트가 거절
}

# 시스템 메일 템플릿 - 변경 요청 (alteration_request 생성)
ALTERATION_REQUESTED_TEMPLATES = {
    "reservation/alteration/alteration_requested",  # 예약 변경 요청
    "ALTERATION_REQUESTED",  # 대문자 버전
}

# 시스템 메일 템플릿 - 완전 스킵 (무시)
SKIP_TEMPLATES = {
    # 리뷰 관련
    "HOME_REVIEW_REMINDER_TO_HOST",  # 후기 요청
    "HOME_REVIEWS_GUEST_REVIEW_TO_HOST",  # 게스트가 남긴 후기
    "HOME_REVIEWS_HOST_REVIEW_REMINDER",  # 호스트 후기 작성 리마인더
    "REVIEW_REMINDER",  # 리뷰 요청
    "GUEST_REVIEW_RECEIVED",  # 게스트 후기 도착
    # 정산/결제 관련
    "PAYMENTS_HOST_PAYOUT_SENT_BASE_2025",  # 대금 지급
    "PAYOUT_SENT",  # 정산 완료
    "PAYOUT_FAILED",  # 정산 실패
    # 리마인더
    "CHECKOUT_REMINDER",  # 체크아웃 리마인더
    "CHECKIN_REMINDER",  # 체크인 리마인더
    "BOOKING_RESERVATION_REMINDER_TO_HOST",  # 곧 체크인 예정 리마인더
    # 기타
    "CALENDAR_SYNC",  # 캘린더 동기화
    "LISTING_QUALITY",  # 숙소 품질 알림
}

# 게스트 메시지 템플릿 (conversation/message 저장 O)
GUEST_MESSAGE_TEMPLATES = {
    "MESSAGING_NEW_MESSAGE_EMAIL_DIGEST",  # 새 메시지 알림
}

# 예약 문의 템플릿 (conversation/message 저장 + inquiry_context)
BOOKING_INQUIRY_TEMPLATES = {
    "BOOKING_INITIAL_INQUIRY",  # 예약 전 문의
    "INQUIRY_NEW_INQUIRY",  # 문의 (예약 전)
}


def _classify_email_type(x_template: Optional[str]) -> str:
    """
    X-Template 헤더 기반으로 이메일 타입 분류.
    
    Returns:
        - "system_booking_confirmation": 예약 확정 → reservation_info 생성 (status=confirmed)
        - "system_cancellation": 취소 → reservation_info status 업데이트 (status=canceled)
        - "system_alteration_accepted": 변경 수락 → alteration_request 처리 + reservation_info 날짜 업데이트
        - "system_alteration_declined": 변경 거절 → alteration_request 상태만 업데이트
        - "system_alteration_requested": 변경 요청 → alteration_request 생성
        - "system_skip": 무시 → 완전 스킵
        - "guest_message": 게스트 메시지 → conversation/message 저장
        - "booking_inquiry": 예약 문의 → conversation/message + inquiry_context
        - "unknown": 알 수 없음 → 기존 로직으로 처리
    """
    if not x_template:
        return "unknown"
    
    # 원본 값과 대문자 버전 모두 확인 (슬래시 포함 패턴 대응)
    template_original = x_template.strip()
    template_upper = template_original.upper()
    
    # 예약 확정
    if template_upper in BOOKING_CONFIRMATION_TEMPLATES:
        return "system_booking_confirmation"
    
    # 취소
    if template_upper in CANCELLATION_TEMPLATES:
        return "system_cancellation"
    
    # 변경 수락
    if template_upper in ALTERATION_ACCEPTED_TEMPLATES:
        return "system_alteration_accepted"
    
    # 변경 거절
    if template_upper in ALTERATION_DECLINED_TEMPLATES:
        return "system_alteration_declined"
    
    # 변경 요청 (슬래시 포함 패턴은 원본으로 체크)
    if template_original in ALTERATION_REQUESTED_TEMPLATES or template_upper in {t.upper() for t in ALTERATION_REQUESTED_TEMPLATES}:
        return "system_alteration_requested"
    
    # 스킵
    if template_upper in SKIP_TEMPLATES or template_upper in {t.upper() for t in SKIP_TEMPLATES}:
        return "system_skip"
    
    # 게스트 메시지
    if template_upper in GUEST_MESSAGE_TEMPLATES:
        return "guest_message"
    
    # 예약 문의
    if template_upper in BOOKING_INQUIRY_TEMPLATES:
        return "booking_inquiry"
    
    # X-Template이 있지만 알려진 패턴이 아님
    return "unknown"


# -------------------------------------------------------------------
# 예약 정보 파싱 (시스템 메일 및 게스트 메시지에서 공통 사용)
# -------------------------------------------------------------------

@dataclass
class ParsedReservationInfo:
    """파싱된 예약 정보"""
    guest_name: Optional[str] = None
    guest_count: Optional[int] = None
    child_count: Optional[int] = None
    infant_count: Optional[int] = None
    pet_count: Optional[int] = None
    reservation_code: Optional[str] = None
    checkin_date: Optional[date] = None
    checkout_date: Optional[date] = None
    checkin_time: Optional[str] = None
    checkout_time: Optional[str] = None
    nights: Optional[int] = None
    total_price: Optional[int] = None
    host_payout: Optional[int] = None
    listing_name: Optional[str] = None


def _parse_guest_count(text: str) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    게스트 인원 파싱.
    예: "성인 4명", "성인 2명, 어린이 1명, 반려동물 1마리"
    
    Returns:
        (guest_count, child_count, infant_count, pet_count)
    """
    guest_count = None
    child_count = None
    infant_count = None
    pet_count = None
    
    # 성인
    adult_match = re.search(r'성인\s*(\d+)\s*명', text)
    if adult_match:
        guest_count = int(adult_match.group(1))
    
    # 어린이
    child_match = re.search(r'어린이\s*(\d+)\s*명', text)
    if child_match:
        child_count = int(child_match.group(1))
    
    # 유아
    infant_match = re.search(r'유아\s*(\d+)\s*명', text)
    if infant_match:
        infant_count = int(infant_match.group(1))
    
    # 반려동물
    pet_match = re.search(r'반려동물\s*(\d+)\s*마리', text)
    if pet_match:
        pet_count = int(pet_match.group(1))
    
    return guest_count, child_count, infant_count, pet_count


def _parse_reservation_code(text: str) -> Optional[str]:
    """
    예약 코드 파싱.
    예: "예약 코드\nHM4WAHCJ2D" 또는 "예약 코드: HM4WAHCJ2D"
    또는 URL에서: /reservations/details/HMB8RYSB8Y
    """
    # 패턴 1: 예약 코드 + 줄바꿈 + 코드
    match = re.search(r'예약\s*코드\s*\n\s*([A-Z0-9]+)', text)
    if match:
        return match.group(1)
    
    # 패턴 2: 예약 코드: 코드
    match = re.search(r'예약\s*코드[:\s]+([A-Z0-9]+)', text)
    if match:
        return match.group(1)
    
    # 패턴 3: URL에서 추출 (변경 완료 이메일 등)
    # /reservations/details/HMB8RYSB8Y 또는 confirmationCode=HMFPECYBEB
    match = re.search(r'/reservations/details/([A-Z0-9]+)', text)
    if match:
        return match.group(1)
    
    match = re.search(r'confirmationCode=([A-Z0-9]+)', text)
    if match:
        return match.group(1)
    
    # 패턴 4: 취소 이메일 제목에서 추출
    # "취소됨: 2026년 2월 10일~11일 예약 건(HMFPECYBEB)"
    match = re.search(r'예약\s*건\s*\(([A-Z0-9]+)\)', text)
    if match:
        return match.group(1)
    
    return None


def _parse_price_info(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    금액 정보 파싱.
    예: "₩220,000 x 1 박  ₩220,000"
    
    Returns:
        (total_price, host_payout) - 호스트 수령액은 별도 패턴 필요
    """
    total_price = None
    host_payout = None
    
    # 총액 (₩ 또는 원화)
    # 패턴: "게스트가 결제한 금액" 섹션에서
    price_match = re.search(r'[₩\￦]\s*([\d,]+)\s*x\s*\d+\s*박\s*[₩\￦]?\s*([\d,]+)', text)
    if price_match:
        total_price = int(price_match.group(2).replace(',', ''))
    
    # 호스트 수령액
    payout_match = re.search(r'호스트\s*수령액[:\s]*[₩\￦]?\s*([\d,]+)', text)
    if payout_match:
        host_payout = int(payout_match.group(1).replace(',', ''))
    
    return total_price, host_payout


def _parse_checkin_checkout_time(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    체크인/체크아웃 시간 파싱.
    예: "오후 4:00", "오전 11:00"
    
    Returns:
        (checkin_time, checkout_time) - "16:00", "11:00" 형식
    """
    checkin_time = None
    checkout_time = None
    
    # 체크인 시간: "체크인" 근처의 시간
    checkin_pattern = r'체크인[^\n]*\n[^\n]*?(오전|오후)\s*(\d{1,2}):(\d{2})'
    checkin_match = re.search(checkin_pattern, text)
    if checkin_match:
        ampm = checkin_match.group(1)
        hour = int(checkin_match.group(2))
        minute = checkin_match.group(3)
        if ampm == "오후" and hour != 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
        checkin_time = f"{hour:02d}:{minute}"
    
    # 체크아웃 시간
    checkout_pattern = r'체크아웃[^\n]*\n[^\n]*?(오전|오후)\s*(\d{1,2}):(\d{2})'
    checkout_match = re.search(checkout_pattern, text)
    if checkout_match:
        ampm = checkout_match.group(1)
        hour = int(checkout_match.group(2))
        minute = checkout_match.group(3)
        if ampm == "오후" and hour != 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
        checkout_time = f"{hour:02d}:{minute}"
    
    return checkin_time, checkout_time


def _parse_reservation_info_from_email(
    text_body: Optional[str],
    html_body: Optional[str],
    subject: Optional[str] = None,
) -> ParsedReservationInfo:
    """
    이메일 본문에서 예약 정보 파싱.
    시스템 메일(예약 확정)과 게스트 메시지 모두에서 사용.
    """
    info = ParsedReservationInfo()
    
    text = text_body or ""
    html = html_body or ""
    combined = f"{text}\n{html}"
    
    # 게스트 인원
    info.guest_count, info.child_count, info.infant_count, info.pet_count = _parse_guest_count(combined)
    
    # 예약 코드
    info.reservation_code = _parse_reservation_code(combined)
    
    # 금액
    info.total_price, info.host_payout = _parse_price_info(combined)
    
    # 체크인/체크아웃 시간
    info.checkin_time, info.checkout_time = _parse_checkin_checkout_time(combined)
    
    return info


def _extract_pure_guest_message(text_body: str) -> str:
    """
    게스트 메시지 이메일에서 순수 메시지만 추출.
    예약 정보, 링크, 푸터 등의 노이즈 제거.
    
    패턴:
        [이름]
        [예약자|게스트]
        [순수 메시지 - 추출 대상]
        
        원문에서 자동 번역된 메시지:
        [번역 원문]
        
        [노이즈 시작 - 제거]
        답장 보내기
        이 이메일에 직접 회신하여...
    """
    if not text_body:
        return ""
    
    # 노이즈 제거 마커들 (마커 이후 내용 전체 제거)
    noise_markers = [
        "답장 보내기",
        "이 이메일에 직접 회신하여",
        "에어비앤비를 가장 쉽고 빠르게",
        "도움말 센터",
        "개인정보 처리방침",
        "[오픈특가]",  # 숙소 정보 시작
        "체크인             체크아웃",  # 예약 정보 테이블
        "체크인\n",
        "게스트\n성인",  # 인원 정보
        "문의 확인하기",  # 예약 문의 이메일 노이즈 (이후 URL도 함께 제거됨)
    ]
    
    result = text_body
    
    # 노이즈 마커 이후 내용 제거
    for marker in noise_markers:
        if marker in result:
            result = result.split(marker)[0]
    
    # "원문에서 자동 번역된 메시지:" 이후 번역 원문도 포함 (옵션)
    # 일단은 번역 원문 이전까지만 추출
    if "원문에서 자동 번역된 메시지:" in result:
        result = result.split("원문에서 자동 번역된 메시지:")[0]
    
    return result.strip()


# -------------------------------------------------------------------
# Gmail API 호출 + Airbnb 메일 파싱
# -------------------------------------------------------------------


@dataclass
class ExtractedMessageBlock:
    """이메일 본문에서 분리된 개별 메시지 블록"""
    sender_name: str
    sender_role: str  # "예약자", "게스트", "호스트"
    content: str
    order: int  # 이메일 내 순서 (0부터)


def _is_valid_sender_name(name: str) -> bool:
    """
    sender_name이 유효한 사람 이름인지 검증.
    
    에어비앤비 이메일의 예약 정보 섹션에 있는 "게스트" 라벨이
    메시지 블록으로 잘못 인식되는 것을 방지.
    
    무효한 케이스:
    - 빈 문자열
    - 공백만 있는 문자열
    - URL 포함
    - 숫자로만 구성
    - 예약 정보 관련 키워드 (체크인, 체크아웃, 오전, 오후 등)
    - 너무 긴 문자열 (50자 초과 - 일반적인 이름이 아님)
    """
    if not name or not name.strip():
        return False
    
    name = name.strip()
    
    # 너무 긴 문자열은 이름이 아님
    if len(name) > 50:
        return False
    
    # URL 포함 시 무효
    if "http" in name.lower() or "www." in name.lower():
        return False
    
    # 숫자로만 구성된 경우 무효
    if name.replace(" ", "").isdigit():
        return False
    
    # 예약 정보/시스템 라벨 키워드가 포함된 경우 무효
    invalid_keywords = [
        "체크인", "체크아웃", "오전", "오후",
        "년", "월", "일",  # 날짜 패턴
        "토요일", "일요일", "월요일", "화요일", "수요일", "목요일", "금요일",
        "답장 보내기", "앱 다운로드",
        "예약 코드", "예약코드",
        "성인", "어린이", "유아", "반려동물",  # 게스트 수 정보
        "숙소", "집 전체", "호스팅",
    ]
    for keyword in invalid_keywords:
        if keyword in name:
            return False
    
    return True


def _split_message_blocks(text_body: str) -> List[ExtractedMessageBlock]:
    """
    에어비앤비 이메일 본문에서 개별 메시지 블록을 분리.
    
    패턴:
        [이름]
        [예약자|게스트|호스트]
        [메시지 내용...]
    
    Returns:
        분리된 메시지 블록 리스트 (이메일 내 순서대로)
    """
    if not text_body:
        return []
    
    # 메시지 블록 시작 패턴: 이름 + 줄바꿈 + 역할(예약자/게스트/호스트) + 줄바꿈
    # 역할 라벨 뒤에 오는 내용이 실제 메시지
    pattern = r'([^\n]+)\n\s*(예약자|게스트|호스트)\s*\n'
    
    matches = list(re.finditer(pattern, text_body))
    
    if not matches:
        return []
    
    blocks: List[ExtractedMessageBlock] = []
    block_order = 0
    
    for i, match in enumerate(matches):
        sender_name = match.group(1).strip()
        sender_role = match.group(2).strip()
        
        # 🔹 유효한 sender_name인지 검증
        # 예약 정보 섹션의 "게스트" 라벨 등을 필터링
        if not _is_valid_sender_name(sender_name):
            continue
        
        content_start = match.end()
        
        # 다음 블록 시작점 또는 텍스트 끝까지가 이 메시지의 내용
        if i + 1 < len(matches):
            content_end = matches[i + 1].start()
        else:
            content_end = len(text_body)
        
        content = text_body[content_start:content_end].strip()
        
        # 에어비앤비 푸터/광고 등 잡음 제거 (선택적)
        # "에어비앤비를 가장 쉽고 빠르게" 같은 문구 이후는 잘라냄
        noise_markers = [
            "에어비앤비를 가장 쉽고 빠르게",
            "도움말 센터",
            "개인정보 처리방침",
            "이 메시지는",
        ]
        for marker in noise_markers:
            if marker in content:
                content = content.split(marker)[0].strip()
        
        if content:  # 내용이 있는 경우만 추가
            blocks.append(ExtractedMessageBlock(
                sender_name=sender_name,
                sender_role=sender_role,
                content=content,
                order=block_order,
            ))
            block_order += 1
    
    return blocks


def _parse_single_message(msg: dict, db: Session) -> List[ParsedInternalMessage]:
    """
    Gmail 메시지 1개를 파싱하여 ParsedInternalMessage 리스트 반환.
    
    에어비앤비 이메일은 하나의 메일에 여러 메시지가 포함될 수 있음.
    예: 게스트 질문 + 호스트 답변이 하나의 이메일에 묶여서 옴.
    
    Returns:
        분리된 메시지별 ParsedInternalMessage 리스트
    """
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
    reply_to = _get_header("Reply-To") or ""  # Reply-To 헤더 추출
    date_str = _get_header("Date")
    
    # 🔹 X-Template 헤더 파싱 (이메일 타입 분류용)
    x_template = _get_header("X-Template")
    email_type = _classify_email_type(x_template)

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
    # BOOKING_INITIAL_INQUIRY는 전용 파서 사용
    if email_type == "booking_inquiry":
        guest_name = _extract_guest_name_for_inquiry(
            subject=subject,
            text=text_body,
            html=html_body,
        )
        checkin_date, checkout_date = _extract_dates_for_inquiry(
            text=text_body,
            html=html_body,
            received_at=received_at,
        )
    else:
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
    
    # 🔹 예약 정보 파싱 (인원, 예약코드, 금액, 시간)
    reservation_info = _parse_reservation_info_from_email(text_body, html_body, subject)
    
    # 🔹 Airbnb Thread ID 추출 (gmail_thread_id와 별개)
    airbnb_thread_id = _extract_airbnb_thread_id(text_body, html_body)
    
    # 🔹 변경 요청 메일인 경우 alteration 정보 파싱
    alteration_id = None
    original_checkin = None
    original_checkout = None
    requested_checkin = None
    requested_checkout = None
    
    if email_type == "system_alteration_requested":
        alteration_id = _extract_alteration_id(text_body, html_body)
        alteration_dates = _parse_alteration_request_dates(text_body, html_body, received_at)
        original_checkin = alteration_dates.original_checkin
        original_checkout = alteration_dates.original_checkout
        requested_checkin = alteration_dates.requested_checkin
        requested_checkout = alteration_dates.requested_checkout
        # 변경 요청 메일에서 listing_name, guest_name 추출
        if alteration_dates.listing_name:
            listing_name = alteration_dates.listing_name
        if alteration_dates.guest_name:
            guest_name = alteration_dates.guest_name
    
    # 🔹 변경 수락/거절 메일인 경우 reservation_code 추출 (URL에서)
    if email_type in ("system_alteration_accepted", "system_alteration_declined"):
        url_reservation_code = _extract_reservation_code_from_url(text_body, html_body)
        if url_reservation_code:
            reservation_info.reservation_code = url_reservation_code
    
    # 공통 필드 준비
    common_fields = {
        "gmail_thread_id": gmail_thread_id,
        "from_email": from_addr,
        "reply_to": reply_to,  # Reply-To 헤더
        "subject": subject,
        "received_at": received_at,
        "snippet": snippet,
        "ota": "airbnb",
        "ota_listing_id": listing_id,
        "ota_listing_name": listing_name,
        "property_code": property_code,
        "guest_name": guest_name,
        "checkin_date": checkin_date,
        "checkout_date": checkout_date,
        "x_template": x_template,
        "email_type": email_type,
        # 예약 정보
        "guest_count": reservation_info.guest_count,
        "child_count": reservation_info.child_count,
        "infant_count": reservation_info.infant_count,
        "pet_count": reservation_info.pet_count,
        "reservation_code": reservation_info.reservation_code,
        "nights": reservation_info.nights,
        "total_price": reservation_info.total_price,
        "host_payout": reservation_info.host_payout,
        "checkin_time": reservation_info.checkin_time,
        "checkout_time": reservation_info.checkout_time,
        # Airbnb Thread ID
        "airbnb_thread_id": airbnb_thread_id,
        # 변경 요청 정보
        "alteration_id": alteration_id,
        "original_checkin": original_checkin,
        "original_checkout": original_checkout,
        "requested_checkin": requested_checkin,
        "requested_checkout": requested_checkout,
    }

    # 🔹 시스템 메일인 경우: 메시지 분리 없이 전체를 하나로 반환
    # system_booking_confirmation, system_cancellation, system_alteration_accepted,
    # system_alteration_declined, system_alteration_requested, system_skip 모두 포함
    if email_type and email_type.startswith("system_"):
        return [ParsedInternalMessage(
            id=gmail_message_id,
            decoded_text_body=text_body,
            decoded_html_body=html_body,
            sender_role=None,
            **common_fields,
        )]

    # 🔹 게스트 메시지인 경우: 메시지 블록 분리 시도
    message_blocks = _split_message_blocks(text_body)
    
    # 메시지 블록이 없으면 이메일 전체를 하나의 메시지로 처리
    # 단, pure_message 추출 적용
    if not message_blocks:
        pure_message = _extract_pure_guest_message(text_body) if text_body else text_body
        return [ParsedInternalMessage(
            id=gmail_message_id,
            decoded_text_body=pure_message,
            decoded_html_body=html_body,
            sender_role=None,
            **common_fields,
        )]
    
    # 메시지 블록이 있으면 각각 별도의 ParsedInternalMessage로 생성
    result: List[ParsedInternalMessage] = []
    
    for block in message_blocks:
        # 각 블록별로 고유 ID 생성 (gmail_message_id + suffix)
        msg_id = f"{gmail_message_id}_{block.order}" if len(message_blocks) > 1 else gmail_message_id
        
        # 게스트 이름: 예약자/게스트 역할인 경우 sender_name 사용
        block_guest_name = guest_name
        if block.sender_role in ("예약자", "게스트"):
            block_guest_name = block.sender_name
        
        # 블록 내용에서 순수 메시지 추출
        pure_content = _extract_pure_guest_message(block.content)
        
        result.append(ParsedInternalMessage(
            id=msg_id,
            decoded_text_body=pure_content,
            decoded_html_body=None,  # 분리된 블록은 text만
            sender_role=block.sender_role,
            guest_name=block_guest_name,
            # 나머지 공통 필드 (guest_name 제외)
            gmail_thread_id=gmail_thread_id,
            from_email=from_addr,
            reply_to=reply_to,
            subject=subject,
            received_at=received_at,
            snippet=snippet,
            ota="airbnb",
            ota_listing_id=listing_id,
            ota_listing_name=listing_name,
            property_code=property_code,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            x_template=x_template,
            email_type=email_type,
            guest_count=reservation_info.guest_count,
            child_count=reservation_info.child_count,
            infant_count=reservation_info.infant_count,
            pet_count=reservation_info.pet_count,
            reservation_code=reservation_info.reservation_code,
            nights=reservation_info.nights,
            total_price=reservation_info.total_price,
            host_payout=reservation_info.host_payout,
            checkin_time=reservation_info.checkin_time,
            checkout_time=reservation_info.checkout_time,
            # 🔹 v4 fix: airbnb_thread_id 누락 수정
            airbnb_thread_id=airbnb_thread_id,
        ))
    
    return result


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

    # ✅ 이미 처리된 gmail_message_id 조회 (Gmail API 호출 최적화)
    from app.repositories.messages import IncomingMessageRepository
    msg_repo = IncomingMessageRepository(db)
    all_msg_ids = [meta["id"] for meta in msg_metas]
    existing_ids = msg_repo.get_existing_gmail_message_ids(all_msg_ids)
    
    new_count = len(msg_metas) - len(existing_ids)
    print(f"[gmail_airbnb] 총 {len(msg_metas)}개 중 {len(existing_ids)}개는 이미 처리됨 → {new_count}개만 처리")

    # ✅ 메일을 오래된 순서로 처리 (BOOKING_CONFIRMATION이 MESSAGE보다 먼저 처리되도록)
    # Gmail API는 최신순으로 반환하므로 역순 정렬
    msg_metas_reversed = list(reversed(msg_metas))
    print(f"[gmail_airbnb] 메일 처리 순서: 오래된 것부터 (역순 정렬)")

    parsed_list: List[ParsedInternalMessage] = []

    for idx, meta in enumerate(msg_metas_reversed, start=1):
        msg_id = meta["id"]
        
        # ✅ 이미 처리된 메시지는 Gmail API 호출 자체를 스킵
        if msg_id in existing_ids:
            print(f"[{idx}] gmail_message_id: {msg_id} → SKIP (already processed)")
            continue

        full_msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )

        # 이제 _parse_single_message는 List를 반환함
        parsed_messages = _parse_single_message(full_msg, db=db)
        parsed_list.extend(parsed_messages)

        print("================================================================================")
        print(f"[{idx}] gmail_message_id: {msg_id} → {len(parsed_messages)}개 메시지 분리")
        
        for sub_idx, parsed in enumerate(parsed_messages):
            print(f"  [{sub_idx}] id: {parsed.id}")
            print(f"      sender_role: {parsed.sender_role}")
            print(f"      guest_name: {parsed.guest_name}")
            if parsed.decoded_text_body:
                preview = parsed.decoded_text_body[:150].replace("\n", "\\n")
                print(f"      content: {preview}...")
        
        # 첫 번째 메시지 기준으로 메타 정보 출력
        if parsed_messages:
            first = parsed_messages[0]
            print(f"    from:    {first.from_email}")
            print(f"    subject: {first.subject}")
            if first.ota_listing_id:
                print(
                    f"[LISTING_ID DETECTED] rooms/ ID: {first.ota_listing_id} "
                    f"(name: {first.ota_listing_name}, property_code={first.property_code})"
                )
            if first.checkin_date or first.checkout_date:
                print(f"    stay: {first.checkin_date} ~ {first.checkout_date}")

        print("================================================================================\n")

    print(f"[gmail_airbnb] 총 {len(msg_metas)}개 이메일에서 {len(parsed_list)}건의 메시지를 파싱했습니다.")
    return parsed_list
