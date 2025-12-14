# backend/app/api/v1/properties.py
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.property_profile_repository import PropertyProfileRepository
from app.domain.models.property_profile import PropertyProfile

router = APIRouter(prefix="/properties", tags=["properties"])


# --- Pydantic Schemas ---


class PropertyProfileBase(BaseModel):
    name: str = Field(..., description="숙소/객실 이름")
    locale: str = Field("ko-KR", description="기본 언어 (예: ko-KR, en-US)")

    checkin_from: str | None = Field(None, description="체크인 시작 시간 (HH:MM)")
    #checkin_to: str | None = Field(None, description="체크인 종료 시간 (HH:MM)")
    checkout_until: str | None = Field(None, description="체크아웃 마감 시간 (HH:MM)")

    parking_info: str | None = None
    pet_policy: str | None = None
    smoking_policy: str | None = None
    noise_policy: str | None = None

    amenities: dict[str, Any] | None = None

    address_summary: str | None = None
    location_guide: str | None = None
    access_guide: str | None = None

    house_rules: str | None = None
    space_overview: str | None = None

    extra_metadata: dict[str, Any] | None = None

    is_active: bool = True


class PropertyProfileCreate(PropertyProfileBase):
    property_code: str = Field(..., description="TONO 내부 숙소 코드 (예: PV-B)")


class PropertyProfileUpdate(PropertyProfileBase):
    # property_code 는 업데이트 시 변경하지 않는다는 가정
    pass


class PropertyProfileRead(PropertyProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    property_code: str


# --- 헬퍼 ---


def _to_read_model(profile: PropertyProfile) -> PropertyProfileRead:
    return PropertyProfileRead.model_validate(profile)


# --- API Endpoints ---


@router.get("", response_model=List[PropertyProfileRead])
def list_properties(
    *,
    db: Session = Depends(get_db),
    active_only: bool = True,
) -> List[PropertyProfileRead]:
    repo = PropertyProfileRepository(db)
    profiles = repo.list_all(active_only=active_only)
    return [_to_read_model(p) for p in profiles]


@router.get("/{property_code}", response_model=PropertyProfileRead)
def get_property(
    *,
    db: Session = Depends(get_db),
    property_code: str,
) -> PropertyProfileRead:
    repo = PropertyProfileRepository(db)
    profile = repo.get_by_property_code(property_code, active_only=False)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PropertyProfile not found",
        )
    return _to_read_model(profile)


@router.post(
    "/",
    response_model=PropertyProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_property(
    *,
    db: Session = Depends(get_db),
    data: PropertyProfileCreate,
) -> PropertyProfileRead:
    repo = PropertyProfileRepository(db)

    # 중복 property_code 방지
    existing = repo.get_by_property_code(data.property_code, active_only=False)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="property_code already exists",
        )

    profile = repo.create(data.model_dump())

    # 🔥 여기서 commit 해줘야 실제 DB에 반영됨
    db.commit()
    db.refresh(profile)

    return _to_read_model(profile)


@router.put(
    "/{property_code}",
    response_model=PropertyProfileRead,
)
def update_property(
    *,
    db: Session = Depends(get_db),
    property_code: str,
    data: PropertyProfileUpdate,
) -> PropertyProfileRead:
    repo = PropertyProfileRepository(db)
    profile = repo.get_by_property_code(property_code, active_only=False)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PropertyProfile not found",
        )

    profile = repo.update(profile, data.model_dump())

    # 🔥 수정 후에도 commit 필요
    db.commit()
    db.refresh(profile)

    return _to_read_model(profile)


@router.delete("/{property_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(
    *,
    db: Session = Depends(get_db),
    property_code: str,
) -> None:
    repo = PropertyProfileRepository(db)
    profile = repo.get_by_property_code(property_code, active_only=False)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PropertyProfile not found",
        )
    repo.soft_delete(profile)

    # 🔥 soft_delete 도 flush만 하니까, 여기서 commit
    db.commit()
