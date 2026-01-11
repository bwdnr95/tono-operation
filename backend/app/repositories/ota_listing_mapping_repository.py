from __future__ import annotations

from typing import Sequence, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.ota_listing_mapping import OtaListingMapping


class OtaListingMappingRepository:
    """
    OTA 리스팅 → property_code/group_code 매핑 전용 레포.
    
    매핑 케이스:
    - 독채: property_code="ABC01", group_code=NULL
    - 그룹+객실확정: property_code="2S28", group_code="2S"
    - 그룹+객실미확정: property_code=NULL, group_code="2S"
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
    
    # 별칭 (기존 코드 호환)
    def get_by_ota_listing_id(
        self,
        *,
        ota: str,
        listing_id: str,
        active_only: bool = True,
    ) -> OtaListingMapping | None:
        """get_by_ota_and_listing_id의 별칭"""
        return self.get_by_ota_and_listing_id(
            ota=ota,
            listing_id=listing_id,
            active_only=active_only,
        )
    
    def get_property_and_group_codes(
        self,
        *,
        ota: str,
        listing_id: str,
        active_only: bool = True,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        OTA 리스팅에서 property_code와 group_code 조회
        
        Returns:
            (property_code, group_code) 튜플
            - 매핑 없으면 (None, None)
            - 독채: ("ABC01", None)
            - 그룹+객실확정: ("2S28", "2S")
            - 그룹+객실미확정: (None, "2S")
        """
        mapping = self.get_by_ota_and_listing_id(
            ota=ota,
            listing_id=listing_id,
            active_only=active_only,
        )
        if mapping is None:
            return (None, None)
        return (mapping.property_code, mapping.group_code)

    def list_all(
        self,
        *,
        ota: str | None = None,
        property_code: str | None = None,
        group_code: str | None = None,
        active_only: bool = True,
    ) -> Sequence[OtaListingMapping]:
        stmt = select(OtaListingMapping)
        if ota:
            stmt = stmt.where(OtaListingMapping.ota == ota)
        if property_code:
            stmt = stmt.where(OtaListingMapping.property_code == property_code)
        if group_code:
            stmt = stmt.where(OtaListingMapping.group_code == group_code)
        if active_only:
            stmt = stmt.where(OtaListingMapping.is_active.is_(True))
        return self.session.execute(stmt).scalars().all()
    
    def list_by_group_code(
        self,
        *,
        group_code: str,
        active_only: bool = True,
    ) -> Sequence[OtaListingMapping]:
        """특정 그룹에 속한 모든 매핑 조회"""
        return self.list_all(group_code=group_code, active_only=active_only)

    # --- 생성/수정 ---

    def upsert(
        self,
        *,
        ota: str,
        listing_id: str,
        property_code: str | None = None,
        group_code: str | None = None,
        listing_name: str | None = None,
        active: bool = True,
    ) -> OtaListingMapping:
        """
        (ota, listing_id) 기준 upsert.

        - 기존 매핑이 있으면 property_code, group_code, listing_name, is_active 업데이트
        - 없으면 새로 생성
        
        Args:
            ota: OTA 타입 (airbnb, booking 등)
            listing_id: OTA 리스팅 ID
            property_code: 숙소 코드 (그룹 매핑 시 NULL 가능)
            group_code: 그룹 코드 (독채 시 NULL)
            listing_name: 리스팅 이름
            active: 활성화 여부
        """
        # 유효성 검사: property_code와 group_code 중 최소 하나는 있어야 함
        if property_code is None and group_code is None:
            raise ValueError("property_code와 group_code 중 최소 하나는 필요합니다")
        
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
                group_code=group_code,
                listing_name=listing_name,
                is_active=active,
            )
            self.session.add(mapping)
        else:
            mapping.property_code = property_code
            mapping.group_code = group_code
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
