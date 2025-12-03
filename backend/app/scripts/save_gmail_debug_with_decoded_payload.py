import json
import base64
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_fetch_service import get_gmail_service
from app.adapters.gmail_airbnb import extract_email_content_from_gmail_message


def _decode_base64url(data: str) -> str:
    """
    Gmail payload.body.data / parts[].body.data 에 들어있는
    base64url 인코딩 문자열을 디코딩해서 str로 반환.
    """
    if not data:
        return ""

    # padding 맞추기
    padding = 4 - (len(data) % 4)
    if padding and padding != 4:
        data += "=" * padding

    try:
        decoded_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        return f"[DECODE_ERROR] {e}"


def _extract_text_from_payload(payload: dict):
    """
    Gmail message의 payload 구조를 그대로 돌면서
    text/plain, text/html 내용을 재귀적으로 디코딩해서 추출.
    """
    text_parts = []
    html_parts = []

    if not payload:
        return "", ""

    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")

    # 단일 파트 (text/plain, text/html 등)
    if data:
        decoded = _decode_base64url(data)
        if mime_type.startswith("text/plain"):
            text_parts.append(decoded)
        elif mime_type.startswith("text/html"):
            html_parts.append(decoded)

    # 멀티파트라면 하위 parts 재귀 탐색
    for part in payload.get("parts", []) or []:
        t, h = _extract_text_from_payload(part)
        if t:
            text_parts.append(t)
        if h:
            html_parts.append(h)

    # 여러 파트가 있을 수 있으니 구분선 넣어서 이어붙이기
    text_body = "\n\n----- [TEXT PART SPLIT] -----\n\n".join(text_parts) if text_parts else ""
    html_body = "\n\n----- [HTML PART SPLIT] -----\n\n".join(html_parts) if html_parts else ""

    return text_body, html_body


def debug_gmail_messages_with_payload(max_results: int = 3):
    """
    Gmail API에서 Airbnb 메일을 가져와서

    1) raw JSON 전체 메시지 저장
    2) 우리가 만든 adapter(extract_email_content_from_gmail_message) 결과 출력
    3) payload를 직접 디코딩한 text/html를 별도 JSON으로 저장 + 콘솔 프린트

    => snippet이 잘리는 문제, payload 구조 문제를 눈으로 디버깅하기 위한 용도
    """
    db: Session = SessionLocal()
    try:
        service = get_gmail_service(db)

        # 👉 여기서 query를 마음대로 바꾸면서 실험 가능
        #   - ""                    : 전체 메일
        #   - "from:airbnb.com"     : Airbnb 관련 메일
        #   - "newer_than:3d"       : 최근 3일 메일
        query = "from:(airbnb.com)"

        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = result.get("messages", [])
        print(f"[DEBUG] Gmail에서 가져온 message 리스트 개수: {len(messages)}")

        if not messages:
            print("[DEBUG] 가져온 메일이 없습니다. query 조건을 바꾸거나, 실제 Airbnb 메일이 있는지 확인하세요.")
            return

        # backend/ 기준으로 debug_gmail 디렉토리 생성
        base_dir = Path(__file__).resolve().parents[2]  # backend/
        debug_dir = base_dir / "debug_gmail"
        debug_dir.mkdir(exist_ok=True)
        print(f"[DEBUG] raw & decoded JSON은 여기 저장됩니다: {debug_dir}")

        decoded_dump = []  # 한 번에 모아서 저장할 리스트

        for idx, m in enumerate(messages, start=1):
            msg_id = m["id"]
            print(f"\n================ [MESSAGE {idx}] id={msg_id} ================")

            full_msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            # 1) raw JSON 파일로 저장
            raw_json_path = debug_dir / f"gmail_message_{msg_id}_raw.json"
            with open(raw_json_path, "w", encoding="utf-8") as f:
                json.dump(full_msg, f, ensure_ascii=False, indent=2)
            print(f"[DEBUG] raw JSON 저장: {raw_json_path.name}")

            # 2) adapter로 파싱 결과 확인 (기존 로직이 실제로 어떻게 동작하는지 비교용)
            (
                gmail_message_id,
                gmail_thread_id,
                from_addr,
                subject,
                text_body_adapter,
                html_body_adapter,
                received_at,
            ) = extract_email_content_from_gmail_message(full_msg)

            print("  [ADAPTER 결과]")
            print("    - gmail_message_id :", gmail_message_id)
            print("    - gmail_thread_id  :", gmail_thread_id)
            print("    - from_addr        :", from_addr)
            print("    - subject          :", subject)
            print("    - received_at      :", received_at)

            if text_body_adapter:
                preview = text_body_adapter[:200].replace("\n", "\\n")
                print(f"    - text_body_adapter (앞 200자): {preview} ...")
            else:
                print("    - text_body_adapter 없음")

            # 3) payload를 직접 디코딩해서 text/html 추출
            payload = full_msg.get("payload", {})
            decoded_text, decoded_html = _extract_text_from_payload(payload)

            print("\n  [PAYLOAD 직접 디코딩 결과]")
            if decoded_text:
                preview_text = decoded_text[:300].replace("\n", "\\n")
                print(f"    - decoded_text (앞 300자): {preview_text} ...")
            else:
                print("    - decoded_text 없음")

            if decoded_html:
                preview_html = decoded_html[:300].replace("\n", "\\n")
                print(f"    - decoded_html (앞 300자): {preview_html} ...")
            else:
                print("    - decoded_html 없음")

            # 4) 디코딩 결과를 별도 JSON으로 저장
            decoded_json = {
                "id": full_msg.get("id"),
                "threadId": full_msg.get("threadId"),
                "snippet": full_msg.get("snippet"),
                "from": from_addr,
                "subject": subject,
                "received_at": str(received_at) if received_at else None,
                "decoded_text_body": decoded_text,
                "decoded_html_body": decoded_html,
            }

            decoded_path = debug_dir / f"gmail_message_{msg_id}_decoded.json"
            with open(decoded_path, "w", encoding="utf-8") as f:
                json.dump(decoded_json, f, ensure_ascii=False, indent=2)
            print(f"[DEBUG] payload 디코딩 JSON 저장: {decoded_path.name}")

            decoded_dump.append(decoded_json)

        # 5) 전체 메시지 디코딩 결과를 한 번에 모은 파일도 저장
        dump_path = debug_dir / "gmail_messages_decoded_dump.json"
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(decoded_dump, f, ensure_ascii=False, indent=2)
        print(f"\n[DEBUG] 전체 디코딩 결과 dump 저장: {dump_path.name}")

    finally:
        db.close()


if __name__ == "__main__":
    # 필요하면 max_results 조절해서 여러 메일 확인 가능
    debug_gmail_messages_with_payload(max_results=20)