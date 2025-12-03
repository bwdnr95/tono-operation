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
        LLM_API_KEY: str | None = None
        LLM_MODEL: str = "gpt-4.1-mini"

settings = Settings()