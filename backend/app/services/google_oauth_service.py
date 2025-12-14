from __future__ import annotations

import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.google_token_repository import (
    upsert_google_token,
    get_google_token,
)

# ---------------------------------------------------------
# Google OAuth 기본 설정
# ---------------------------------------------------------
GOOGLE_AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


# ---------------------------------------------------------
# 1) Google OAuth URL 생성
# ---------------------------------------------------------
def build_google_auth_url() -> str:
    """
    FastAPI에서 사용자가 Google OAuth 로그인하도록
    Google Authorization URL을 만들어주는 함수.
    """
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": " ".join(
            [
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.send",
            ]
        ),
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTH_BASE_URL}?{urlencode(params)}"


# ---------------------------------------------------------
# 2) Authorization Code → Access/Refresh Token 교환
# ---------------------------------------------------------
def exchange_code_for_tokens(db: Session, *, code: str):
    """
    OAuth Callback에서 Authorization Code를 받아
    Access Token + Refresh Token으로 교환한 뒤 DB에 저장.
    """
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    resp = requests.post(GOOGLE_TOKEN_URL, data=data)
    resp.raise_for_status()
    token_data = resp.json()

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data["expires_in"]
    token_type = token_data.get("token_type", "Bearer")
    scope = token_data.get("scope", "")

    # 🔥 naive UTC 기준으로 저장 (DB DateTime과 맞춤)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    email = settings.GMAIL_USER
    if not email:
        raise RuntimeError("GMAIL_USER가 설정되지 않았습니다. .env에 GMAIL_USER 추가 필요")

    # DB에 토큰 저장
    return upsert_google_token(
        db=db,
        email=email,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        scope=scope,
        expires_at=expires_at,
    )


# ---------------------------------------------------------
# 3) Access Token 만료 시 자동 Refresh
# ---------------------------------------------------------
def refresh_google_access_token(db: Session, *, email: str):
    """
    refresh_token을 사용해서 access_token 자동 갱신.
    """
    token = get_google_token(db, email=email)
    if not token:
        raise RuntimeError("Google token not found in DB. 로그인 먼저 필요합니다.")

    if not token.refresh_token:
        raise RuntimeError("refresh_token이 없습니다. 다시 Google OAuth 로그인해야 합니다.")

    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": token.refresh_token,
        "grant_type": "refresh_token",
    }

    resp = requests.post(GOOGLE_TOKEN_URL, data=data)
    resp.raise_for_status()
    token_data = resp.json()

    new_access_token = token_data["access_token"]
    expires_in = token_data["expires_in"]

    # 🔥 naive UTC로 맞춤
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # DB 업데이트 후 반환
    return upsert_google_token(
        db=db,
        email=email,
        access_token=new_access_token,
        refresh_token=token.refresh_token,
        token_type="Bearer",
        scope=token.scope,
        expires_at=expires_at,
    )


# ---------------------------------------------------------
# 4) Gmail API 클라이언트 생성 함수 (핵심)
# ---------------------------------------------------------
def get_gmail_service(db: Session):
    """
    TONO 시스템에서 Gmail API를 사용할 때 항상 이 함수를 호출.

    1. DB에서 access_token / refresh_token 읽기
    2. access_token 만료 시 refresh_token으로 자동 갱신
    3. Google API Python Client로 Gmail service 생성
    """
    email = settings.GMAIL_USER
    token = get_google_token(db, email=email)
    if not token:
        raise RuntimeError("Google token not found. Google OAuth 로그인 필요합니다.")

    # 🔥 현재 시각 (naive UTC)
    now_utc = datetime.utcnow()

    # 🔥 4-1) Access Token 만료되었으면 자동 refresh
    if token.expires_at is None or token.expires_at < now_utc:
        print("🔄 Access Token expired 또는 만료시간 없음 → Refreshing...")
        token = refresh_google_access_token(db, email=email)

    # 🔥 4-2) Credentials 객체 생성
    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=token.scope.split() if token.scope else [],
    )

    # 🔥 4-3) Gmail API 클라이언트 생성
    gmail = build("gmail", "v1", credentials=creds)
    return gmail
