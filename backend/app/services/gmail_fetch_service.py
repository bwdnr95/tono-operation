from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.google_token_repository import get_google_token

def get_gmail_service(db: Session):
    token = get_google_token(db, settings.GMAIL_USER)
    if not token:
        raise RuntimeError("GoogleToken이 없습니다. 먼저 OAuth 연동을 진행하세요.")

    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
        ],
    )

    service = build("gmail", "v1", credentials=creds)
    return service