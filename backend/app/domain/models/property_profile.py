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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PropertyProfile(Base):
    """
    숙소 지식 컨텍스트를 저장하는 모델.

    - property_code: TONO 내부 숙소 코드 (Airbnb listing 여러 개가 이 코드로 묶일 수 있음)
    - name: 숙소/객실 이름
    - locale: 기본 언어 (예: "ko-KR", "en-US")
    """

    __tablename__ = "property_profiles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    property_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # 소속 그룹 코드 (NULL이면 독채/그룹 없음)
    group_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    locale: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ko-KR",
    )

    # ===== 체크인 / 체크아웃 시간 =====
    # 예: "15:00", "12:00" 등의 문자열로 관리
    checkin_from: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    # checkin_to 컬럼은 DB에서 삭제했으므로 ORM에서도 제거
    checkout_until: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    # ===== 위치 / 주소 / 안내 =====
    # 상세 주소
    address_full: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    
    # 주소 노출 정책: 'always' (예약 확정시) | 'checkin_day' (체크인 당일, 기본값)
    address_disclosure_policy: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default="checkin_day",
    )

    # 간단 요약 주소/위치 설명 (기존 필드)
    address_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_guide: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ===== 공간 / 구조 정보 =====
    # 집 구조 설명 (예: "복층 구조 1층 침실 1개·화장실 2개, 2층 침실 1개·주방·테라스")
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

    # 침대 타입 설명 (예: "퀸사이즈 침대 3개 (1층 1개, 2층 2개)")
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

    # 기준/최대 인원
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
    # 예: DOORLOCK_SELF_CHECKIN, MEET_AND_GREET 등
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
    # 구조: [{"key": "string", "category": "string", "answer": "string"}]
    faq_entries: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )

    # ===== iCal 연동 =====
    ical_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    ical_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    def __repr__(self) -> str:
        return f"<PropertyProfile id={self.id} code={self.property_code} name={self.name}>"
