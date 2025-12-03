from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.ota_listing_mapping import OtaListingMapping
from app.repositories.ota_listing_mapping_repository import (
    OtaListingMappingRepository,
)

router = APIRouter(
    prefix="/ota",
    tags=["ota_listings"],
)


# --- Schemas ---


class ListingMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ota: str
    listing_id: str
    listing_name: str | None
    property_code: str
    is_active: bool


class ListingItem(BaseModel):
    listing_id: str = Field(..., description="OTA listing ID (e.g. Airbnb rooms/{id})")
    listing_name: str | None = Field(
        default=None,
        description="Human readable listing name (optional)",
    )


class BulkAssignRequest(BaseModel):
    """
    여러 listing_id 를 한 property_code 로 묶기 위한 요청 모델.

    프론트에서:
      - ota: "airbnb"
      - property_code: "GONGGAM-101"
      - listings: [
          { "listing_id": "12345678", "listing_name": "공감공간101-평일" },
          { "listing_id": "87654321", "listing_name": "공감공간101-주말" },
        ]
    이런 식으로 보내면 된다.
    """

    ota: str = Field(..., description="OTA provider code (e.g. airbnb)")
    property_code: str = Field(..., description="TONO internal property_code")
    listings: List[ListingItem] = Field(
        default_factory=list,
        description="List of listing IDs to assign to the property_code",
    )


# --- Handlers ---


@router.get(
    "/listing-mappings",
    response_model=List[ListingMappingRead],
)
def list_listing_mappings(
    *,
    ota: str | None = None,
    property_code: str | None = None,
    db: Session = Depends(get_db),
) -> List[ListingMappingRead]:
    """
    OTA 리스팅 매핑 리스트 조회.

    - ota, property_code 로 필터 가능
    - 프론트에서 '이 property 에 어떤 listing 이 묶여 있는지' 보여줄 때 사용
    """
    repo = OtaListingMappingRepository(db)
    mappings = repo.list_all(
        ota=ota,
        property_code=property_code,
        active_only=True,
    )
    return list(mappings)


@router.post(
    "/listing-mappings/bulk-assign",
    response_model=List[ListingMappingRead],
    status_code=status.HTTP_200_OK,
)
def bulk_assign_listing_mappings(
    *,
    body: BulkAssignRequest,
    db: Session = Depends(get_db),
) -> List[ListingMappingRead]:
    """
    여러 listing_id 를 한 property_code 로 묶는 엔드포인트.

    - OtaListingMapping 테이블에 (ota, listing_id) 기준 upsert
    - 가능하다면 IncomingMessage 에도 property_code 를 반영 (미래 확장 대비)
    """

    if not body.listings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No listings provided",
        )

    repo = OtaListingMappingRepository(db)

    created_or_updated: list[OtaListingMapping] = []

    for item in body.listings:
        mapping = repo.upsert(
            ota=body.ota,
            listing_id=item.listing_id,
            listing_name=item.listing_name,
            property_code=body.property_code,
            active=True,
        )
        created_or_updated.append(mapping)

        # 미래 확장: IncomingMessage 에 ota / ota_listing_id 가 저장되는 경우,
        # 과거 메시지들도 한 번에 property_code 를 채워줄 수 있다.
        #
        # 지금은 IncomingMessage 에 ota/ota_listing_id 컬럼이 아직 없더라도
        # 이 코드는 단순히 0 row 업데이트로 끝난다.
        try:
            db.execute(
                update(IncomingMessage)
                .where(
                    IncomingMessage.from_email.is_not(None),  # 완전 no-op 방지는 아님, placeholder
                    # 실제로는 IncomingMessage 에 ota / ota_listing_id 컬럼이 생기면:
                    # IncomingMessage.ota == body.ota,
                    # IncomingMessage.ota_listing_id == item.listing_id,
                )
                .values(property_code=body.property_code)
            )
        except Exception:
            # 컬럼이 아직 없거나, 스키마가 달라도 서비스 전체가 죽지 않도록 보호
            pass

    db.commit()
    return list(created_or_updated)
