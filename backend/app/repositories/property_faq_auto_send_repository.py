# backend/app/repositories/property_faq_auto_send_repository.py
"""
Property + FAQ Key별 AUTO_SEND 통계 Repository
"""
from typing import Optional, List

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.domain.models.property_faq_auto_send_stats import PropertyFaqAutoSendStats


class PropertyFaqAutoSendRepository:
    """PropertyFaqAutoSendStats CRUD"""
    
    def __init__(self, db: Session):
        self._db = db
    
    def get_by_property_and_faq_key(
        self, 
        property_code: str, 
        faq_key: str
    ) -> Optional[PropertyFaqAutoSendStats]:
        """property_code + faq_key로 조회"""
        stmt = select(PropertyFaqAutoSendStats).where(
            and_(
                PropertyFaqAutoSendStats.property_code == property_code,
                PropertyFaqAutoSendStats.faq_key == faq_key,
            )
        )
        return self._db.execute(stmt).scalar()
    
    def get_or_create(
        self, 
        property_code: str, 
        faq_key: str
    ) -> PropertyFaqAutoSendStats:
        """있으면 반환, 없으면 생성"""
        existing = self.get_by_property_and_faq_key(property_code, faq_key)
        if existing:
            return existing
        
        stats = PropertyFaqAutoSendStats(
            property_code=property_code,
            faq_key=faq_key,
        )
        self._db.add(stats)
        self._db.flush()
        return stats
    
    def get_eligible_for_property(
        self, 
        property_code: str
    ) -> List[PropertyFaqAutoSendStats]:
        """특정 숙소의 AUTO_SEND 가능한 faq_key 목록"""
        stmt = select(PropertyFaqAutoSendStats).where(
            and_(
                PropertyFaqAutoSendStats.property_code == property_code,
                PropertyFaqAutoSendStats.eligible_for_auto_send == True,
            )
        ).order_by(PropertyFaqAutoSendStats.approval_rate.desc())
        return list(self._db.execute(stmt).scalars().all())
    
    def get_all_for_property(
        self, 
        property_code: str
    ) -> List[PropertyFaqAutoSendStats]:
        """특정 숙소의 모든 통계"""
        stmt = select(PropertyFaqAutoSendStats).where(
            PropertyFaqAutoSendStats.property_code == property_code
        ).order_by(PropertyFaqAutoSendStats.total_count.desc())
        return list(self._db.execute(stmt).scalars().all())
    
    def get_all_eligible(self) -> List[PropertyFaqAutoSendStats]:
        """모든 AUTO_SEND 가능한 통계"""
        stmt = select(PropertyFaqAutoSendStats).where(
            PropertyFaqAutoSendStats.eligible_for_auto_send == True
        ).order_by(
            PropertyFaqAutoSendStats.property_code,
            PropertyFaqAutoSendStats.approval_rate.desc(),
        )
        return list(self._db.execute(stmt).scalars().all())
    
    def is_eligible_for_auto_send(
        self, 
        property_code: str, 
        faq_keys: List[str]
    ) -> bool:
        """
        주어진 property_code와 faq_keys 조합이 AUTO_SEND 가능한지 판단.
        모든 faq_keys가 eligible이어야 True.
        """
        if not faq_keys:
            return False
        
        for faq_key in faq_keys:
            stats = self.get_by_property_and_faq_key(property_code, faq_key)
            if not stats or not stats.eligible_for_auto_send:
                return False
        
        return True
    
    def record_approved(
        self, 
        property_code: str, 
        faq_keys: List[str],
    ) -> None:
        """수정 없이 승인 기록 (성공)"""
        for faq_key in faq_keys:
            stats = self.get_or_create(property_code, faq_key)
            stats.record_approved()
    
    def record_edited(
        self, 
        property_code: str, 
        faq_keys: List[str],
    ) -> None:
        """수정함 기록 (실패)"""
        for faq_key in faq_keys:
            stats = self.get_or_create(property_code, faq_key)
            stats.record_edited()
