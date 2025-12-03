# backend/app/scripts/init_db.py

from app.db.session import init_db


def main() -> None:
    init_db()
    print("✅ DB 초기화 완료: 모든 테이블이 생성되었습니다.")


if __name__ == "__main__":
    main()
