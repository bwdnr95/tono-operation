import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.gmail_fetch_service import get_gmail_service
from app.adapters.gmail_airbnb import extract_email_content_from_gmail_message


def debug_gmail_messages(max_results: int = 3):
    """
    Gmail API에서 Airbnb 메일을 가져와서
    - raw JSON 파일로 저장
    - 파싱 결과를 콘솔에 출력
    """
    db: Session = SessionLocal()
    try:
        service = get_gmail_service(db)

        # 👉 여기서 query를 마음대로 바꾸면서 실험 가능
        #   - ""               : 전체 메일
        #   - "from:airbnb.com": Airbnb 관련 메일
        #   - "newer_than:3d"  : 최근 3일 메일
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

        # debug 파일 저장 경로: backend/debug_gmail/
        base_dir = Path(__file__).resolve().parents[2]  # backend/
        debug_dir = base_dir / "debug_gmail"
        debug_dir.mkdir(exist_ok=True)
        print(f"[DEBUG] raw JSON은 여기 저장됩니다: {debug_dir}")

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
            json_path = debug_dir / f"gmail_message_{msg_id}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(full_msg, f, ensure_ascii=False, indent=2)
            print(f"[DEBUG] raw JSON 저장: {json_path.name}")

            # 2) 우리가 만든 adapter로 파싱 결과 확인
            (
                gmail_message_id,
                gmail_thread_id,
                from_addr,
                subject,
                text_body,
                html_body,
                received_at,
            ) = extract_email_content_from_gmail_message(full_msg)

            print("  - gmail_message_id :", gmail_message_id)
            print("  - gmail_thread_id  :", gmail_thread_id)
            print("  - from_addr        :", from_addr)
            print("  - subject          :", subject)
            print("  - received_at      :", received_at)

            # text_body / html_body가 너무 길 수 있으니 앞부분만 잘라서 보여주기
            if text_body:
                preview = text_body[:300].replace("\n", "\\n")
                print(f"  - text_body (앞 300자): {preview} ...")
            else:
                print("  - text_body 없음")

            if html_body:
                preview_html = html_body[:300].replace("\n", "\\n")
                print(f"  - html_body (앞 300자): {preview_html} ...")
            else:
                print("  - html_body 없음")

    finally:
        db.close()


if __name__ == "__main__":
    # 필요하면 max_results 조절해서 여러 메일 확인 가능
    debug_gmail_messages(max_results=20)