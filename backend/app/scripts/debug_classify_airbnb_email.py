"""
Airbnb 이메일 디버그용 스크립트.

사용 예:
    python -m app.scripts.debug_classify_airbnb_email --file path/to/debug_email.json

debug_email.json 의 예시는 Gmail 디버그 저장본
(id, subject, snippet, decoded_text_body, decoded_html_body 등 포함) 형식.
"""

import argparse
import json
from pathlib import Path
from app.services.airbnb_guest_message_extractor import (
    extract_guest_message_segment,
)

from app.services.airbnb_message_origin_classifier import (
    classify_airbnb_message_origin,
)
from app.services.airbnb_intent_classifier import (
    classify_airbnb_guest_intent,
)
from app.domain.intents import MessageActor, MessageActionability


def load_email_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_message_preview(
    decoded_text_body: str,
    max_lines: int = 20,
    max_chars: int = 1000,
) -> str:
    """
    디버그용 게스트 메세지 프리뷰.

    - 공백/빈 줄 제거
    - 최대 max_lines 줄까지만 사용
    - 전체 길이는 max_chars 로 컷
    """
    if not decoded_text_body:
        return "(decoded_text_body 가 비어 있습니다)"

    # 줄 단위로 나눈 뒤, 공백 줄 제거
    lines = [line for line in decoded_text_body.splitlines() if line.strip()]

    if not lines:
        return "(유효한 텍스트 라인이 없습니다)"

    # 위에서부터 max_lines 줄까지만 사용
    preview_text = "\n".join(lines[:max_lines])

    # 너무 길면 글자 수 자르기
    if len(preview_text) > max_chars:
        preview_text = preview_text[:max_chars] + "\n...[이후 생략]"

    return preview_text


def pretty_print_origin(origin) -> None:
    print("=== [1] Origin Classification (게스트/호스트/시스템) ===")
    print(f"- actor          : {origin.actor.value}")
    print(f"- actionability  : {origin.actionability.value}")
    print(f"- confidence     : {origin.confidence:.2f}")
    if origin.raw_role_label:
        print(f"- raw_role_label : {origin.raw_role_label}")
    if origin.reasons:
        print("- reasons:")
        for r in origin.reasons:
            print(f"  • {r}")
    print()


def pretty_print_intent(intent_result) -> None:
    print("=== [2] Intent Classification (게스트 메시지 의도) ===")
    print(f"- intent         : {intent_result.intent.name}")
    print(f"- confidence     : {intent_result.confidence:.2f}")
    print(f"- is_ambiguous   : {intent_result.is_ambiguous}")
    if intent_result.secondary_intent:
        print(
            f"- secondary      : {intent_result.secondary_intent.name} "
            f"({intent_result.secondary_confidence:.2f})"
        )
    if intent_result.reasons:
        print("- reasons:")
        for r in intent_result.reasons:
            print(f"  • {r}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Airbnb 디버그 이메일(JSON)에 대해 Origin/Intent 분류 결과를 출력합니다."
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="디버그 JSON 파일 경로 (decoded_text_body 포함)",
    )

    args = parser.parse_args()
    path = Path(args.file)

    data = load_email_json(path)

    # 디버그 JSON에서 필요한 필드 추출 (병욱님이 보여준 예시 기준)
    decoded_text_body = data.get("decoded_text_body") or ""
    decoded_html_body = data.get("decoded_html_body")
    subject = data.get("subject")
    snippet = data.get("snippet")

    print("=== Airbnb 디버그 이메일 분류 시작 ===")
    print(f"- 파일   : {path}")
    print(f"- subject: {subject}")
    print()

    # ✅ [0] 게스트 메세지 텍스트 프리뷰
    print("=== [0] 게스트 메세지 (텍스트 본문 요약) ===")
    preview = build_message_preview(decoded_text_body)
    print(preview)
    print()

    # ✅ [0-1] 게스트 '순수 메시지' 추출본
    print("=== [0-1] 게스트 순수 메시지 (추출 결과) ===")
    pure_guest_message = extract_guest_message_segment(decoded_text_body)
    print(pure_guest_message if pure_guest_message else "(추출된 게스트 메시지가 없습니다)")
    print()
    
    # 1) Origin 분류 (게스트/호스트/시스템 + actionability)
    origin = classify_airbnb_message_origin(
        decoded_text_body=decoded_text_body,
        decoded_html_body=decoded_html_body,
        subject=subject,
        snippet=snippet,
    )
    pretty_print_origin(origin)

    # 2) 게스트 + 답변 필요인 경우에만 Intent 분류
    if (
        origin.actor == MessageActor.GUEST
        and origin.actionability == MessageActionability.NEEDS_REPLY
    ):
        intent_result = classify_airbnb_guest_intent(
            decoded_text_body=decoded_text_body,
            subject=subject,
            snippet=snippet,
        )
        pretty_print_intent(intent_result)
    else:
        print(
            "⚠ 이 메시지는 게스트 문의가 아니거나, "
            "TONO가 답변이 필요하다고 판단하지 않은 메일입니다."
        )
        print(
            "  → Intent 분류는 건너뜁니다 "
            "(예: 호스트가 보낸 체크인 안내, 시스템 알림, 우리가 보낸 메일 사본 등)."
        )
    print()
    print("=== 분류 종료 ===")


if __name__ == "__main__":
    main()