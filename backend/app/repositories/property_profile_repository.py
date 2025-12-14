# backend/app/repositories/property_profile_repository.py
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.property_profile import PropertyProfile


class PropertyProfileRepository:
    """
    PropertyProfile 전용 레포지토리.
    """

    def __init__(self, session: Session):
        self.session = session

    # --- 조회 ---

    def get_by_id(self, id_: int) -> PropertyProfile | None:
        return self.session.get(PropertyProfile, id_)

    def get_by_property_code(
        self,
        property_code: str,
        active_only: bool = True,
    ) -> PropertyProfile | None:
        stmt = select(PropertyProfile).where(
            PropertyProfile.property_code == property_code,
        )
        if active_only:
            stmt = stmt.where(PropertyProfile.is_active.is_(True))
        return self.session.execute(stmt).scalar_one_or_none()

    def list_all(
        self,
        *,
        active_only: bool = True,
    ) -> Sequence[PropertyProfile]:
        stmt = select(PropertyProfile)
        if active_only:
            stmt = stmt.where(PropertyProfile.is_active.is_(True))
        stmt = stmt.order_by(PropertyProfile.property_code.asc())
        return self.session.execute(stmt).scalars().all()

    # --- 생성/수정/삭제 ---

    def create(self, data: dict) -> PropertyProfile:
        profile = PropertyProfile(**data)
        self.session.add(profile)
        self.session.flush()
        return profile

    def update(
        self,
        profile: PropertyProfile,
        data: dict,
    ) -> PropertyProfile:
        for k, v in data.items():
            if hasattr(profile, k):
                setattr(profile, k, v)
        self.session.flush()
        return profile

    def soft_delete(self, profile: PropertyProfile) -> None:
        profile.is_active = False
        self.session.flush()
