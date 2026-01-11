# backend/app/services/property_resolver.py
"""
Property Resolver - Single Source of Truth for property_code/group_code

설계 원칙:
- reservation_info가 property_code/group_code의 유일한 진실의 원천
- incoming_message.property_code는 수신 시점 스냅샷 (참고용)
- conversation.property_code는 deprecated (향후 제거 예정)

사용법:
    resolver = PropertyResolver(db)
    
    # property_code, group_code 모두 조회
    prop, group = resolver.resolve(airbnb_thread_id)
    
    # property_code만 필요할 때
    prop = resolver.resolve_property_code(airbnb_thread_id)
    
    # group_code만 필요할 때  
    group = resolver.resolve_group_code(airbnb_thread_id)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.reservation_info import ReservationInfo
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.property_profile import PropertyProfile

logger = logging.getLogger(__name__)


@dataclass
class ResolvedProperty:
    """Property 조회 결과"""
    property_code: Optional[str] = None
    group_code: Optional[str] = None
    source: str = "none"  # reservation_info | message_snapshot | property_profile | none
    
    @property
    def has_property(self) -> bool:
        return self.property_code is not None
    
    @property
    def has_group(self) -> bool:
        return self.group_code is not None
    
    @property
    def has_any(self) -> bool:
        return self.has_property or self.has_group


class PropertyResolver:
    """
    Property/Group 코드 조회 서비스
    
    조회 우선순위:
    1. reservation_info (Single Source of Truth)
    2. property_profile에서 group_code 보완 (property_code는 있는데 group_code 없을 때)
    3. incoming_message (fallback - reservation_info 없을 때만)
    """
    
    def __init__(self, db: Session):
        self._db = db
    
    def resolve(self, airbnb_thread_id: str) -> ResolvedProperty:
        """
        airbnb_thread_id로 property_code, group_code 조회
        
        Returns:
            ResolvedProperty with property_code, group_code, source
        """
        if not airbnb_thread_id:
            return ResolvedProperty()
        
        # 1. reservation_info에서 조회 (Single Source of Truth)
        reservation = self._db.execute(
            select(ReservationInfo)
            .where(ReservationInfo.airbnb_thread_id == airbnb_thread_id)
        ).scalar_one_or_none()
        
        if reservation:
            property_code = reservation.property_code
            group_code = reservation.group_code
            
            # property_code는 있는데 group_code가 없으면 property_profile에서 보완
            if property_code and not group_code:
                group_code = self._get_group_from_property(property_code)
            
            if property_code or group_code:
                return ResolvedProperty(
                    property_code=property_code,
                    group_code=group_code,
                    source="reservation_info",
                )
        
        # 2. Fallback: incoming_message에서 조회 (reservation_info 없을 때)
        # 예: 예약 확정 전 문의 메시지
        message = self._db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
            .order_by(IncomingMessage.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if message and message.property_code:
            group_code = self._get_group_from_property(message.property_code)
            return ResolvedProperty(
                property_code=message.property_code,
                group_code=group_code,
                source="message_snapshot",
            )
        
        return ResolvedProperty()
    
    def resolve_property_code(self, airbnb_thread_id: str) -> Optional[str]:
        """property_code만 조회"""
        return self.resolve(airbnb_thread_id).property_code
    
    def resolve_group_code(self, airbnb_thread_id: str) -> Optional[str]:
        """group_code만 조회"""
        return self.resolve(airbnb_thread_id).group_code
    
    def resolve_with_message_fallback(
        self,
        airbnb_thread_id: str,
        message_property_code: Optional[str] = None,
    ) -> ResolvedProperty:
        """
        reservation_info 우선, 없으면 전달받은 message.property_code 사용
        
        Args:
            airbnb_thread_id: 스레드 ID
            message_property_code: incoming_message.property_code (fallback용)
        """
        result = self.resolve(airbnb_thread_id)
        
        if result.has_any:
            return result
        
        # Fallback 1: 전달받은 message.property_code 사용
        if message_property_code:
            group_code = self._get_group_from_property(message_property_code)
            return ResolvedProperty(
                property_code=message_property_code,
                group_code=group_code,
                source="message_snapshot",
            )
        
        # 🆕 Fallback 2: conversation.property_code (레거시 데이터 대응)
        from app.domain.models.conversation import Conversation
        conv = self._db.execute(
            select(Conversation)
            .where(Conversation.airbnb_thread_id == airbnb_thread_id)
        ).scalar_one_or_none()
        
        if conv and conv.property_code:
            group_code = self._get_group_from_property(conv.property_code)
            return ResolvedProperty(
                property_code=conv.property_code,
                group_code=group_code,
                source="conversation_legacy",
            )
        
        return ResolvedProperty()
    
    def _get_group_from_property(self, property_code: str) -> Optional[str]:
        """property_profile에서 group_code 조회"""
        profile = self._db.execute(
            select(PropertyProfile.group_code)
            .where(PropertyProfile.property_code == property_code)
        ).scalar_one_or_none()
        return profile


# ============================================================
# 편의 함수 (기존 코드 마이그레이션용)
# ============================================================

def get_effective_property_code(db: Session, airbnb_thread_id: str) -> Optional[str]:
    """
    [편의 함수] property_code 조회
    
    기존 코드에서 msg.property_code, conv.property_code 대신 사용
    """
    return PropertyResolver(db).resolve_property_code(airbnb_thread_id)


def get_effective_group_code(db: Session, airbnb_thread_id: str) -> Optional[str]:
    """
    [편의 함수] group_code 조회
    """
    return PropertyResolver(db).resolve_group_code(airbnb_thread_id)


def get_effective_property_and_group(
    db: Session,
    airbnb_thread_id: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    [편의 함수] property_code, group_code 모두 조회
    
    Returns:
        (property_code, group_code) tuple
    """
    result = PropertyResolver(db).resolve(airbnb_thread_id)
    return result.property_code, result.group_code
