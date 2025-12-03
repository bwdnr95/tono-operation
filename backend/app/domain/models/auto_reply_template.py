from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.sql import func

from app.db.base import Base  # 프로젝트에 이미 존재한다고 가정


class AutoReplyTemplate(Base):
    """
    Intent 기반 자동응답 템플릿 DB 모델.

    - Intent, locale, channel, property_code 축으로 필터링
    - priority, min_intent_confidence 등을 기반으로 추천 우선순위 결정
    """

    __tablename__ = "auto_reply_templates"

    id: int = Column(Integer, primary_key=True, index=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    is_active: bool = Column(Boolean, nullable=False, default=True, index=True)

    # 운영자용 템플릿 이름 (UI에 표시)
    name: str = Column(String(255), nullable=False)

    # TONO GuestIntent Enum의 코드값 (e.g. "CHECKIN_QUESTION")
    intent: str = Column(String(64), nullable=False, index=True)

    # 언어/로케일 (e.g. "ko-KR", "en-US")
    locale: str = Column(String(16), nullable=False, index=True, default="ko-KR")

    # 채널 (airbnb / booking / naver / agoda / generic 등)
    channel: str = Column(String(32), nullable=False, index=True, default="generic")

    # 특정 숙소 전용 템플릿. None이면 글로벌 템플릿으로 사용
    # 실제 FK는 추후 properties 테이블 구조 확정 후 연결 가능
    property_code: Optional[str] = Column(String(64), nullable=True, index=True)

    # 이메일 Subject (필요 없는 채널에서는 NULL 가능)
    subject_template: Optional[str] = Column(String(255), nullable=True)

    # 실제 응답 본문 템플릿 (placeholders 포함)
    body_template: str = Column(Text, nullable=False)

    # 이 템플릿이 사용하는 placeholder 목록 (메타데이터용)
    # 예: ["guest_first_name", "checkin_time"]
    placeholders = Column(JSON, nullable=True)

    # 숫자가 작을수록 높은 우선순위 (0 = 가장 우선)
    priority: int = Column(Integer, nullable=False, default=100, index=True)

    # 이 템플릿이 추천되기 위한 최소 intent confidence
    min_intent_confidence: Optional[float] = Column(Float, nullable=True)

    # (옵션) 상한선. 대부분의 경우 NULL
    max_intent_confidence: Optional[float] = Column(Float, nullable=True)

    # 자동 발송에 사용 가능한 템플릿인지 여부
    auto_send_enabled: bool = Column(Boolean, nullable=False, default=False, index=True)

    # 자동 발송 허용 intent confidence 최대값 (e.g. 0.9)
    # None이면 "추천만" 하고 자동 발송에는 사용하지 않음.
    auto_send_max_confidence: Optional[float] = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AutoReplyTemplate id={self.id} "
            f"intent={self.intent} locale={self.locale} "
            f"channel={self.channel} property={self.property_code}>"
        )
