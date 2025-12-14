from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Float,
    JSON,
)
from sqlalchemy.sql import func

from app.db.base import Base


class AutoReplyTemplate(Base):
    __tablename__ = "auto_reply_templates"

    id: int = Column(Integer, primary_key=True, index=True)

    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 활성화 여부
    is_active: bool = Column(Boolean, nullable=False, default=True)

    # 사람이 읽을 수 있는 템플릿 이름
    name: str = Column(String, nullable=False)

    # 상위 Intent (MessageIntent.name)
    intent: str = Column(String, nullable=False)

    # 언어 (예: 'ko', 'en')
    locale: str = Column(String, nullable=False)

    # 채널 (예: 'airbnb', 'kakao', 'naver', ...)
    channel: str = Column(String, nullable=False)

    # 특정 숙소 전용 템플릿이면 property_code 세팅 (예: 'PV-A', 'PV-B')
    property_code: Optional[str] = Column(String, nullable=True)

    # 제목 템플릿 (지금은 거의 사용 안 함, NULL 허용)
    subject_template: Optional[str] = Column(String, nullable=True)

    # 본문 템플릿 (실제 자동응답 텍스트)
    body_template: str = Column(Text, nullable=False)

    # 플레이스홀더/메타 정보 (JSON)
    placeholders: Optional[Any] = Column(JSON, nullable=True)

    # 우선순위 (숫자 작을수록 우선, 또는 프로젝트 룰에 맞게 사용)
    priority: int = Column(Integer, nullable=False, default=100)

    # Intent confidence 허용 범위
    min_intent_confidence: Optional[float] = Column(Float, nullable=True)
    max_intent_confidence: Optional[float] = Column(Float, nullable=True)

    # 자동 발송 허용 여부
    auto_send_enabled: bool = Column(Boolean, nullable=False, default=False)

    # 자동 발송 허용 상한 (예: 0.98 이상이면 사람 검토)
    auto_send_max_confidence: Optional[float] = Column(Float, nullable=True)

    # 🔥 세분화 Intent (FineGrainedIntent.name)
    #   예: 'HOUSE_RULE_SMOKING_QUESTION', 'AMENITY_WASHER_DRYER_QUESTION'
    fine_intent: Optional[str] = Column(String, nullable=True)
