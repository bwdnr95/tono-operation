
from __future__ import annotations

from typing import List


def _normalize_lines(raw_text: str) -> List[str]:
    """줄 단위로 나누고, 오른쪽 공백 제거."""
    return [line.rstrip("\r") for line in raw_text.splitlines()]


def extract_guest_message_segment(decoded_text_body: str) -> str:
    """
    Airbnb 텍스트형 이메일에서 '게스트가 실제로 쓴 메시지' 부분만 대략 추출.

    현재 규칙 (샘플 기반 휴리스틱):
    - 라인 중에 '게스트' 또는 '예약자' 라벨이 여러 번 나타날 수 있음
    - 가장 마지막 '게스트/예약자' 라벨 이후의 텍스트 블록을 게스트 메시지로 간주
    - '이미지가 전송됨', '답장 보내기', 링크/URL 같은 시스템 문구는 제거

    나중에 샘플이 더 모이면, 이 규칙은 계속 보강/수정할 예정.
    """

    if not decoded_text_body:
        return ""

    lines = _normalize_lines(decoded_text_body)

    # 1) '게스트' / '예약자' 라벨의 마지막 위치 찾기
    role_keywords = {"게스트", "예약자"}
    last_role_idx = -1

    for idx, line in enumerate(lines):
        if line.strip() in role_keywords:
            last_role_idx = idx

    if last_role_idx == -1:
        # 라벨을 못 찾으면 일단 전체를 반환 (향후 개선 포인트)
        return decoded_text_body.strip()

    # 2) 마지막 라벨 이후의 텍스트를 후보로 사용
    candidate_lines: List[str] = []
    for line in lines[last_role_idx + 1 :]:
        stripped = line.strip()

        # 종료 조건: Airbnb 시스템 버튼/링크/푸터 등
        if "답장 보내기" in stripped:
            break
        if stripped.startswith("https://www.airbnb.co.kr/hosting/thread"):
            break

        # 노이즈 제거: 이미지 전송 알림 등
        if "이미지가 전송됨" in stripped:
            continue
        if stripped.startswith("%opentrack%"):
            continue

        # 기타 너무 기술적인/시스템성 라인 제거 (필요시 확장)
        if stripped.startswith("https://"):
            continue

        candidate_lines.append(stripped)

    # 앞뒤 공백 라인 제거
    cleaned = [line for line in candidate_lines if line]

    return "\n".join(cleaned).strip()