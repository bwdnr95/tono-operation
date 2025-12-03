from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.property_profile import PropertyProfile


class PropertyProfileRepository:
    """
    PropertyProfile 전용 Repository.
    - DB CRUD만 담당 (비즈니스 로직 없음)
    """

    def __init__(self, session: Session):
        self.session = session

    # --- 조회 ---

    def get_by_id(self, profile_id: int) -> PropertyProfile | None:
        return self.session.get(PropertyProfile, profile_id)

    def get_by_property_code(
        self,
        property_code: str,
        active_only: bool = True,
    ) -> PropertyProfile | None:
        stmt = select(PropertyProfile).where(
            PropertyProfile.property_code == property_code
        )
        if active_only:
            stmt = stmt.where(PropertyProfile.is_active.is_(True))
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_codes(
        self,
        property_codes: Iterable[str],
        active_only: bool = True,
    ) -> Sequence[PropertyProfile]:
        codes = list(property_codes)
        if not codes:
            return []
        stmt = select(PropertyProfile).where(
            PropertyProfile.property_code.in_(codes)
        )
        if active_only:
            stmt = stmt.where(PropertyProfile.is_active.is_(True))
        return self.session.execute(stmt).scalars().all()

    def list_all(self, active_only: bool = True) -> Sequence[PropertyProfile]:
        stmt = select(PropertyProfile)
        if active_only:
            stmt = stmt.where(PropertyProfile.is_active.is_(True))
        return self.session.execute(stmt).scalars().all()

    # --- 생성/수정/삭제 ---

    def create(self, obj_in: dict) -> PropertyProfile:
        profile = PropertyProfile(**obj_in)
        self.session.add(profile)
        self.session.flush()
        return profile

    def update(
        self,
        profile: PropertyProfile,
        obj_in: dict,
    ) -> PropertyProfile:
        for key, value in obj_in.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        self.session.flush()
        return profile

    def upsert_by_property_code(
        self,
        property_code: str,
        obj_in: dict,
    ) -> PropertyProfile:
        profile = self.get_by_property_code(property_code, active_only=False)
        if profile is None:
            obj_in = {**obj_in, "property_code": property_code}
            return self.create(obj_in=obj_in)
        return self.update(profile, obj_in=obj_in)

    def soft_delete(self, profile: PropertyProfile) -> None:
        profile.is_active = False
        self.session.flush()
