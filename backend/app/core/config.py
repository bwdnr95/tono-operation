# backend/app/core/config.py
import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트 기준으로 .env 로드
BASE_DIR = Path(__file__).resolve().parents[3]
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    def __init__(self) -> None:
        # DB
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://postgres:tono123@localhost:5432/postgres",
        )

        # Google OAuth
        self.GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
        self.GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.GOOGLE_REDIRECT_URI: str = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://localhost:8000/auth/google/callback",
        )

        # Gmail 계정
        self.GMAIL_USER: str = os.getenv("GMAIL_USER", "")

        # LLM 설정
        self.LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")
        
        # 용도별 모델 분리
        # - REPLY: 자동응답 생성 (품질 중요, 고객 대면)
        # - PARSER: 메일 파싱, OC/Commitment 추출 (단순 추출, 비용 절감)
        self.LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4.1")  # 기본값 (하위 호환)
        self.LLM_MODEL_REPLY: str = os.getenv("LLM_MODEL_REPLY", "gpt-4.1")
        self.LLM_MODEL_PARSER: str = os.getenv("LLM_MODEL_PARSER", "gpt-4o-mini")


settings = Settings()
