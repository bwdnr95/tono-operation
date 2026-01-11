# backend/app/services/airbnb_guest_message_extractor.py
from __future__ import annotations

from typing import Optional
import re


# 이메일 하단 CTA / FAQ / 푸터 영역을 자르기 위한 패턴들
CTA_PATTERNS = [
    r"예약\s*사전\s*승인",              # 예약 사전 승인 또는 거절
    r"24시간\s*이내에\s*답장해주세요",  # 24시간 이내에 답장해주세요
    r"자주\s*묻는\s*질문",             # FAQ 영역
    r"고객지원",                       # 고객지원 영역
    r"Airbnb Ireland UC",             # 푸터 주소
]


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _strip_obvious_noise_lines(lines: list[str]) -> list[str]:
    """
    트래킹, 완전한 링크 등 '절대 게스트 메시지가 아닌' 라인들을 1차적으로 제거.
    """
    cleaned: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            cleaned.append("")  # 빈 줄은 블록 구분자로 남긴다
            continue

        # 트래킹 토큰
        if s.startswith("%opentrack%"):
            continue

        # pure URL 라인 (FAQ/푸터 링크 등)
        if s.startswith("http://") or s.startswith("https://"):
            if "airbnb.co.kr" in s or "airbnb.com" in s:
                continue

        cleaned.append(line)
    return cleaned


def _cut_before_cta(text: str) -> str:
    """
    CTA(예약 사전 승인, 24시간 이내에 답장해주세요 등) 시작 부분 이전까지만 남긴다.
    여러 패턴 중 '가장 먼저 등장하는 지점' 앞에서 자른다.
    """
    earliest_idx: int | None = None

    for pattern in CTA_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        if earliest_idx is None or m.start() < earliest_idx:
            earliest_idx = m.start()

    if earliest_idx is None:
        return text
    return text[:earliest_idx]


def _last_non_empty_block(text: str) -> Optional[str]:
    """
    텍스트를 줄 단위로 나눈 뒤,
    마지막 '연속된 non-empty 줄 묶음'을 하나의 블록으로 잡아서 반환.
    """
    lines = text.split("\n")

    blocks: list[list[str]] = []
    current: list[str] = []

    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip():
            current.append(line)
        else:
            if current:
                blocks.append(current)
                current = []

    if current:
        blocks.append(current)

    if not blocks:
        return None

    candidate = blocks[-1]
    candidate = [l.strip() for l in candidate]
    return "\n".join(candidate).strip() or None


def _extract_after_profile_block(lines: list[str]) -> Optional[str]:

    base_idx: int | None = None

    # 1순위: "가입 연도" (프로필 영역의 명확한 라벨)
    for i, line in enumerate(lines):
        if "가입 연도" in line:
            base_idx = i
            break

    # 2순위: "South Korea" 또는 국가명 (프로필 위치 정보)
    # "예약자"는 게스트 메시지 내에서도 사용될 수 있으므로 제외
    if base_idx is None:
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 국가명만 있는 라인 (프로필 위치)
            if stripped == "South Korea" or stripped == "Korea" or stripped == "대한민국":
                base_idx = i
                break
    
    # 3순위: "Changwon-si, South Korea" 등 도시명, 국가명 패턴
    if base_idx is None:
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 도시, 국가 패턴 (예: "Changwon-si, South Korea")
            if re.match(r"^[\w\-]+,\s*(South )?Korea$", stripped, re.IGNORECASE):
                base_idx = i
                break

    if base_idx is None:
        return None

    # base_idx 이후 첫 non-empty 라인부터 시작
    j = base_idx + 1
    n = len(lines)

    while j < n and not lines[j].strip():
        j += 1
    if j >= n:
        return None

    start = j
    
    # CTA 패턴이 나올 때까지 또는 끝까지 모두 수집
    # (빈 줄이 있어도 계속 수집 - 게스트 메시지에 문단 구분이 있을 수 있음)
    message_lines: list[str] = []
    k = start
    
    while k < n:
        line = lines[k].strip()
        
        # CTA 패턴을 만나면 중단
        is_cta = False
        for pattern in CTA_PATTERNS:
            if re.search(pattern, line):
                is_cta = True
                break
        if is_cta:
            break
        
        message_lines.append(line)
        k += 1
    
    # 수집된 라인들을 결합하되, 연속된 빈 줄은 하나의 줄바꿈으로 정리
    result_lines: list[str] = []
    prev_empty = False
    
    for line in message_lines:
        if not line:
            if not prev_empty and result_lines:  # 첫 줄이 빈 줄이면 무시
                result_lines.append("")
            prev_empty = True
        else:
            result_lines.append(line)
            prev_empty = False
    
    # 마지막 빈 줄들 제거
    while result_lines and not result_lines[-1]:
        result_lines.pop()
    
    block = "\n".join(result_lines).strip()
    
    return block or None


def extract_guest_message_segment(raw_text_body: str | None) -> Optional[str]:
    """
    Airbnb 호스트용 알림 이메일(text/plain)에서
    '게스트가 실제로 작성한 메시지' 부분만 최대한 정제해서 추출.
    """
    if not raw_text_body:
        return None

    text = _normalize_newlines(raw_text_body)
    lines = text.split("\n")
    lines = _strip_obvious_noise_lines(lines)

    # 1차: 프로필 블록 기준 (문의 / 예약 확정 모두 커버)
    primary = _extract_after_profile_block(lines)
    if primary:
        return primary

    # 2차: CTA 이전까지만 자르고 그 안의 마지막 블록을 사용
    text2 = "\n".join(lines)
    text_before_cta = _cut_before_cta(text2)
    guest_block = _last_non_empty_block(text_before_cta)
    if not guest_block:
        return None

    return guest_block
