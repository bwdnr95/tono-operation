from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.ota_listing_mapping import OtaListingMapping


class OtaListingMappingRepository:
    """
    OTA 리스팅 → property_code 매핑 전용 레포.
    """

    def __init__(self, session: Session):
        self.session = session

    # --- 조회 ---

    def get_by_ota_and_listing_id(
        self,
        *,
        ota: str,
        listing_id: str,
        active_only: bool = True,
    ) -> OtaListingMapping | None:
        stmt = select(OtaListingMapping).where(
            OtaListingMapping.ota == ota,
            OtaListingMapping.listing_id == listing_id,
        )
        if active_only:
            stmt = stmt.where(OtaListingMapping.is_active.is_(True))
        return self.session.execute(stmt).scalar_one_or_none()

    def list_all(
        self,
        *,
        ota: str | None = None,
        property_code: str | None = None,
        active_only: bool = True,
    ) -> Sequence[OtaListingMapping]:
        stmt = select(OtaListingMapping)
        if ota:
            stmt = stmt.where(OtaListingMapping.ota == ota)
        if property_code:
            stmt = stmt.where(OtaListingMapping.property_code == property_code)
        if active_only:
            stmt = stmt.where(OtaListingMapping.is_active.is_(True))
        return self.session.execute(stmt).scalars().all()

    # --- 생성/수정 ---

    def upsert(
        self,
        *,
        ota: str,
        listing_id: str,
        property_code: str,
        listing_name: str | None = None,
        active: bool = True,
    ) -> OtaListingMapping:
        """
        (ota, listing_id) 기준 upsert.

        - 기존 매핑이 있으면 property_code, listing_name, is_active 업데이트
        - 없으면 새로 생성
        """
        mapping = self.get_by_ota_and_listing_id(
            ota=ota,
            listing_id=listing_id,
            active_only=False,
        )

        if mapping is None:
            mapping = OtaListingMapping(
                ota=ota,
                listing_id=listing_id,
                property_code=property_code,
                listing_name=listing_name,
                is_active=active,
            )
            self.session.add(mapping)
        else:
            mapping.property_code = property_code
            if listing_name is not None:
                mapping.listing_name = listing_name
            mapping.is_active = active

        self.session.flush()
        return mapping

    def deactivate(
        self,
        *,
        ota: str,
        listing_id: str,
    ) -> None:
        mapping = self.get_by_ota_and_listing_id(
            ota=ota,
            listing_id=listing_id,
            active_only=False,
        )
        if mapping is None:
            return
        mapping.is_active = False
        self.session.flush()
