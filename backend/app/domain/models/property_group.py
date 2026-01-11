from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    Integer,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PropertyGroup(Base):
    """
    숙소 그룹 모델.
    
    호텔의 객실 타입, 또는 동일 건물 내 여러 객실을 묶는 그룹 개념.
    property_profiles의 상위 개념으로, 그룹 공통 정보를 저장.
    
    상속 규칙:
    - property_profiles 값 우선
    - NULL이면 property_groups에서 상속
    
    사용 케이스:
    - 솔레어 테라스 그룹 (2S) → 2S28, 2S29, 2S30 객실들
    - 공감공간 그룹 (Y) → Y1, Y2, Y3 객실들
    """

    __tablename__ = "property_groups"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    # 그룹 식별자 (예: "2S", "Y")
    group_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # 그룹 이름 (예: "솔레어 테라스", "공감공간")
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 기본 언어
    locale: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ko-KR",
    )

    # ===== 체크인 / 체크아웃 시간 =====
    checkin_from: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    checkout_until: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    # ===== 위치 / 주소 / 안내 =====
    address_full: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    
    address_disclosure_policy: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default="checkin_day",
    )

    address_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_guide: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ===== 공간 / 구조 정보 =====
    floor_plan: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    bedroom_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    bed_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    bed_types: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    bathroom_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    has_elevator: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    capacity_base: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    capacity_max: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    has_terrace: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    # ===== 체크인 방식 =====
    checkin_method: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # ===== 네트워크 / 기본 편의 =====
    wifi_ssid: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    wifi_password: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    towel_count_provided: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    aircon_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    aircon_usage_guide: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    heating_usage_guide: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ===== 추가 침구 =====
    extra_bedding_available: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    extra_bedding_price_info: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ===== 세탁 / 조리 =====
    laundry_guide: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    has_washer: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    has_dryer: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    cooking_allowed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    has_seasonings: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    has_tableware: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    has_rice_cooker: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    # ===== 엔터테인먼트 =====
    has_tv: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    has_projector: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    has_turntable: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    has_wine_opener: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    # ===== 수영장 / 온수풀 =====
    has_pool: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    # 기존 컬럼 (하위 호환용, 추후 삭제 예정)
    hot_pool_fee_info: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # 🆕 새 컬럼들 (구조화)
    pool_fee: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="온수풀 이용료 (예: 100,000원)",
    )
    pool_reservation_notice: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="온수풀 예약 조건 (예: 최소 2일 전 예약 필요)",
    )
    pool_payment_account: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="온수풀 결제 계좌 (예: 카카오뱅크 79420372489 송대섭)",
    )

    # ===== 바베큐 =====
    bbq_available: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    # 기존 컬럼 (하위 호환용, 추후 삭제 예정)
    bbq_guide: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # 🆕 새 컬럼들 (구조화)
    bbq_fee: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="바베큐 이용료 (예: 30,000원)",
    )
    bbq_reservation_notice: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="바베큐 예약 조건 (예: 최소 1일 전 예약 필요)",
    )
    bbq_payment_account: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="바베큐 결제 계좌 (예: 카카오뱅크 79420372489 송대섭)",
    )

    # ===== 정책/하우스 룰 =====
    parking_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    pet_allowed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    pet_policy: Mapped[str | None] = mapped_column(Text, nullable=True)

    smoking_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    noise_policy: Mapped[str | None] = mapped_column(Text, nullable=True)

    house_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    space_overview: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ===== 편의시설 JSON & 메타데이터 =====
    amenities: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    extra_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # ===== FAQ 데이터 =====
    faq_entries: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )

    # ===== 공통 =====
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

    # ===== Relationships =====
    # property_profiles와의 관계 (1:N)
    # properties: Mapped[list["PropertyProfile"]] = relationship(
    #     "PropertyProfile",
    #     back_populates="group",
    #     foreign_keys="PropertyProfile.group_code",
    # )

    def __repr__(self) -> str:
        return f"<PropertyGroup id={self.id} code={self.group_code} name={self.name}>"
