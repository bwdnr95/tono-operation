# backend/app/repositories/google_token_repository.py

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models.google_token import GoogleToken


def get_google_token(db: Session, email: str) -> GoogleToken | None:
    """
    이메일 기준으로 저장된 Google OAuth 토큰 검색.
    """
    stmt = select(GoogleToken).where(GoogleToken.email == email)
    return db.scalar(stmt)


def upsert_google_token(
    db: Session,
    *,
    email: str,
    access_token: str,
    refresh_token: str | None,
    token_type: str,
    scope: str,
    expires_at,
) -> GoogleToken:
    """
    Google OAuth Token을 이메일 기준으로 upsert.
    - 이미 있으면 업데이트
    - 없으면 생성
    """
    token = get_google_token(db, email)

    if token:
        token.access_token = access_token
        if refresh_token:
            token.refresh_token = refresh_token
        token.token_type = token_type
        token.scope = scope
        token.expires_at = expires_at
        db.add(token)
        db.commit()
        db.refresh(token)
        return token

    # 새로 생성
    new_token = GoogleToken(
        email=email,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        scope=scope,
        expires_at=expires_at,
    )
    db.add(new_token)
    db.commit()
    db.refresh(new_token)
    return new_token
