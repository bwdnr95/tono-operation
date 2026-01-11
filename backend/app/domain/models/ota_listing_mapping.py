from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OtaListingMapping(Base):
    """
    OTA 리스팅 ID → TONO property_code 매핑.

    예:
      - ota: "airbnb"
      - listing_id: "12345678"
      - property_code: "GONGGAM-101"

    한 property_code에 여러 listing_id 가 매핑될 수 있다.
    """

    __tablename__ = "ota_listing_mappings"
    __table_args__ = (
        UniqueConstraint("ota", "listing_id", name="uq_ota_listing_mappings_ota_listing"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    # OTA 제공자 코드 (예: "airbnb", "booking", "agoda" 등)
    ota: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    # OTA 내부 리스팅 ID (Airbnb rooms/{id} 의 id 등)
    listing_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    # 사람이 읽기 좋은 리스팅 이름 (옵션)
    listing_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # TONO 내부 property_code (PropertyProfile.property_code)
    # 그룹 매핑 시 NULL 가능
    property_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    # 그룹 매핑 시 사용 (property_code가 NULL일 때 필수)
    # property_code가 있는 경우에도 그룹 소속이면 함께 저장
    group_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
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
            f"<OtaListingMapping id={self.id} ota={self.ota} "
            f"listing_id={self.listing_id} property_code={self.property_code}>"
        )
