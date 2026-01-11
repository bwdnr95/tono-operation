# backend/app/repositories/property_group_repository.py
"""
PropertyGroup Repository

숙소 그룹 조회/관리 레포지토리
"""
from __future__ import annotations

from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.property_group import PropertyGroup


class PropertyGroupRepository:
    """PropertyGroup 조회/관리 레포지토리"""
    
    def __init__(self, db: Session):
        self._db = db
    
    def get_by_group_code(self, group_code: str) -> Optional[PropertyGroup]:
        """group_code로 그룹 조회"""
        stmt = select(PropertyGroup).where(
            PropertyGroup.group_code == group_code,
            PropertyGroup.is_active == True,
        )
        return self._db.execute(stmt).scalar_one_or_none()
    
    def get_all_active(self) -> List[PropertyGroup]:
        """활성화된 모든 그룹 조회"""
        stmt = select(PropertyGroup).where(
            PropertyGroup.is_active == True,
        ).order_by(PropertyGroup.name)
        return list(self._db.execute(stmt).scalars().all())
    
    def create(self, group: PropertyGroup) -> PropertyGroup:
        """그룹 생성"""
        self._db.add(group)
        self._db.flush()
        return group
    
    def update(self, group: PropertyGroup) -> PropertyGroup:
        """그룹 업데이트"""
        self._db.flush()
        return group
    
    def delete(self, group_code: str) -> bool:
        """그룹 비활성화 (soft delete)"""
        group = self.get_by_group_code(group_code)
        if group:
            group.is_active = False
            self._db.flush()
            return True
        return False
    
    def get_first_property_code(self, group_code: str) -> Optional[str]:
        """
        그룹에 속한 첫 번째 property_code 반환
        
        그룹만 있고 property_code가 없는 예약에서 LLM 컨텍스트용 대표 property 조회
        """
        from app.domain.models.property_profile import PropertyProfile
        
        stmt = select(PropertyProfile.property_code).where(
            PropertyProfile.group_code == group_code,
            PropertyProfile.is_active == True,
        ).order_by(PropertyProfile.property_code).limit(1)
        
        result = self._db.execute(stmt).scalar_one_or_none()
        return result
