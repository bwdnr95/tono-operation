from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PropertyProfile(Base):
    """
    숙소별 지식 컨텍스트 모델.

    - property_code 기준으로 고유 식별
    - LLM 컨텍스트로 넘길 수 있는 모든 정형/반정형 정보를 저장
    """

    __tablename__ = "property_profiles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # Airbnb listing ID 또는 내부 코드
    property_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    # 숙소 이름
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 언어/로케일 (예: ko-KR, en-US)
    locale: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ko-KR",
        index=True,
    )

    # 체크인/체크아웃 시간 정보
    checkin_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    checkin_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    checkout_until: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 주차/반려동물/흡연/소음 정책
    parking_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    pet_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    smoking_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    noise_policy: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 편의시설 정보 (JSON)
    # 예: {"wifi": true, "washer": true, "parking_spot_count": 2, ...}
    amenities: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # 주소/위치/이동 안내
    address_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_guide: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 하우스룰, 공간 설명
    house_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    space_overview: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 확장용 메타데이터(JSON)
    # 예: {"tone": "친절하지만 단호하게", "forbidden_words": [...], ...}
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"<PropertyProfile id={self.id} "
            f"code={self.property_code} locale={self.locale} active={self.is_active}>"
        )
