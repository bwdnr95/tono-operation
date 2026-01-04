# backend/app/services/property_faq_auto_send_service.py
"""
Property + FAQ Key별 AUTO_SEND 서비스

draft_replies 발송 시 통계 업데이트하고,
AUTO_SEND 가능 여부를 판단.

승인률 기준:
- is_edited = false → 성공 (수정 없이 승인)
- is_edited = true → 실패 (수정함)
"""
import logging
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from app.repositories.property_faq_auto_send_repository import PropertyFaqAutoSendRepository


logger = logging.getLogger(__name__)


class PropertyFaqAutoSendService:
    """Property + FAQ별 AUTO_SEND 통계 서비스"""
    
    def __init__(self, db: Session):
        self._db = db
        self._repo = PropertyFaqAutoSendRepository(db)
    
    def is_eligible_for_auto_send(
        self,
        property_code: str,
        faq_keys: List[str],
    ) -> bool:
        """
        AUTO_SEND 가능 여부 판단.
        모든 faq_keys가 해당 property에서 eligible 상태여야 함.
        """
        if not property_code or not faq_keys:
            return False
        
        return self._repo.is_eligible_for_auto_send(property_code, faq_keys)
    
    def record_approved(
        self,
        property_code: str,
        faq_keys: List[str],
    ) -> None:
        """수정 없이 승인 (성공)"""
        if not property_code or not faq_keys:
            return
        
        self._repo.record_approved(property_code, faq_keys)
        logger.info(
            "Recorded approved: property_code=%s, faq_keys=%s",
            property_code, faq_keys
        )
    
    def record_edited(
        self,
        property_code: str,
        faq_keys: List[str],
    ) -> None:
        """수정함 (실패)"""
        if not property_code or not faq_keys:
            return
        
        self._repo.record_edited(property_code, faq_keys)
        logger.info(
            "Recorded edited: property_code=%s, faq_keys=%s",
            property_code, faq_keys
        )
    
    def get_stats_for_property(
        self,
        property_code: str,
    ) -> List[Dict[str, Any]]:
        """특정 숙소의 모든 통계"""
        stats = self._repo.get_all_for_property(property_code)
        return [s.to_dict() for s in stats]
    
    def get_eligible_faq_keys(
        self,
        property_code: str,
    ) -> List[str]:
        """특정 숙소의 AUTO_SEND 가능한 faq_key 목록"""
        stats = self._repo.get_eligible_for_property(property_code)
        return [s.faq_key for s in stats]
    
    def get_all_eligible_stats(self) -> List[Dict[str, Any]]:
        """모든 AUTO_SEND 가능한 통계"""
        stats = self._repo.get_all_eligible()
        return [s.to_dict() for s in stats]
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """전체 통계 요약"""
        all_eligible = self._repo.get_all_eligible()
        
        by_property: Dict[str, List[str]] = {}
        for stat in all_eligible:
            if stat.property_code not in by_property:
                by_property[stat.property_code] = []
            by_property[stat.property_code].append(stat.faq_key)
        
        return {
            "total_eligible_count": len(all_eligible),
            "properties_with_auto_send": len(by_property),
            "by_property": by_property,
        }
