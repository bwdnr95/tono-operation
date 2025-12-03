from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.property_profile_repository import PropertyProfileRepository
from app.domain.models.property_profile import PropertyProfile

router = APIRouter(
    prefix="/properties",
    tags=["properties"],
)


# --- Pydantic Schemas ---


class PropertyProfileBase(BaseModel):
    name: str = Field(..., max_length=255)
    locale: str = Field(default="ko-KR", max_length=16)

    checkin_from: str | None = None
    checkin_to: str | None = None
    checkout_until: str | None = None

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
    property_code: str = Field(..., max_length=64)


class PropertyProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    locale: str | None = Field(default=None, max_length=16)

    checkin_from: str | None = None
    checkin_to: str | None = None
    checkout_until: str | None = None

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
    is_active: bool | None = None


class PropertyProfileRead(PropertyProfileBase):
    id: int
    property_code: str

    model_config = ConfigDict(from_attributes=True)


# --- Router Handlers ---


@router.get("/", response_model=List[PropertyProfileRead])
def list_properties(
    *,
    db: Session = Depends(get_db),
    active_only: bool = True,
) -> List[PropertyProfileRead]:
    repo = PropertyProfileRepository(db)
    profiles = repo.list_all(active_only=active_only)
    return list(profiles)


@router.get("/{property_code}", response_model=PropertyProfileRead)
def get_property(
    *,
    db: Session = Depends(get_db),
    property_code: str,
) -> PropertyProfileRead:
    repo = PropertyProfileRepository(db)
    profile = repo.get_by_property_code(property_code)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PropertyProfile not found",
        )
    return profile


@router.post(
    "/",
    response_model=PropertyProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_property(
    *,
    db: Session = Depends(get_db),
    payload: PropertyProfileCreate,
) -> PropertyProfileRead:
    repo = PropertyProfileRepository(db)
    existing = repo.get_by_property_code(payload.property_code, active_only=False)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PropertyProfile with this property_code already exists",
        )
    profile = repo.create(payload.model_dump())
    return profile


@router.put("/{property_code}", response_model=PropertyProfileRead)
def update_property(
    *,
    db: Session = Depends(get_db),
    property_code: str,
    payload: PropertyProfileUpdate,
) -> PropertyProfileRead:
    repo = PropertyProfileRepository(db)
    profile = repo.get_by_property_code(property_code, active_only=False)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PropertyProfile not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    profile = repo.update(profile, update_data)
    return profile


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
