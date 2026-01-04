# backend/app/domain/models/push_subscription.py
"""
Browser Push Notification 구독 정보 모델
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PushSubscription(Base):
    """Push 구독 정보"""
    
    __tablename__ = "push_subscriptions"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # Push 구독 정보
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh_key: Mapped[str] = mapped_column(Text, nullable=False)
    auth_key: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 사용자 식별
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 상태
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<PushSubscription {self.id[:8]}... endpoint={self.endpoint[:50]}...>"
    
    def to_webpush_dict(self) -> dict:
        """pywebpush용 구독 정보 딕셔너리 반환"""
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh_key,
                "auth": self.auth_key,
            }
        }
