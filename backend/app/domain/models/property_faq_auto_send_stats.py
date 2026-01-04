# backend/app/domain/models/property_faq_auto_send_stats.py
"""
Property + FAQ Key별 AUTO_SEND 통계 모델

숙소별 + FAQ키별로 승인률을 추적하여 AUTO_SEND 가능 여부를 판단.

승인률 계산 기준 (draft_replies.is_edited):
- is_edited = false → 성공 (수정 없이 승인)
- is_edited = true → 실패 (수정함)

approval_rate = approved_count / total_count
"""
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, 
    UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db.base import Base


class PropertyFaqAutoSendStats(Base):
    """
    숙소별 + FAQ키별 AUTO_SEND 통계
    
    복합키: (property_code, faq_key)
    승인률 = approved_count / total_count
    """
    __tablename__ = "property_faq_auto_send_stats"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 복합키
    property_code = Column(String(50), nullable=False, index=True)
    faq_key = Column(String(100), nullable=False, index=True)
    
    # 통계
    total_count = Column(Integer, nullable=False, default=0)
    approved_count = Column(Integer, nullable=False, default=0)  # 수정 없이 승인 (성공)
    edited_count = Column(Integer, nullable=False, default=0)    # 수정함 (실패)
    
    # 계산된 값: approved_count / total_count
    approval_rate = Column(Float, nullable=False, default=0.0)
    
    # AUTO_SEND 자격
    eligible_for_auto_send = Column(Boolean, nullable=False, default=False)
    
    # 메타데이터
    last_approved_at = Column(DateTime(timezone=True), nullable=True)
    last_edited_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('property_code', 'faq_key', name='uq_property_faq_key'),
        Index('ix_property_faq_eligible', 'property_code', 'eligible_for_auto_send'),
        CheckConstraint('total_count >= 0', name='ck_total_count_positive'),
        CheckConstraint('approval_rate >= 0 AND approval_rate <= 1', name='ck_approval_rate_range'),
    )
    
    def recalculate_stats(self) -> None:
        """통계 재계산"""
        if self.total_count > 0:
            self.approval_rate = self.approved_count / self.total_count
        else:
            self.approval_rate = 0.0
        
        # AUTO_SEND 자격: 최소 5건 이상, 승인률 80% 이상
        self.eligible_for_auto_send = (
            self.total_count >= 5 and 
            self.approval_rate >= 0.8
        )
    
    def record_approved(self) -> None:
        """수정 없이 승인 (성공)"""
        self.total_count += 1
        self.approved_count += 1
        self.last_approved_at = datetime.utcnow()
        self.recalculate_stats()
    
    def record_edited(self) -> None:
        """수정함 (실패)"""
        self.total_count += 1
        self.edited_count += 1
        self.last_edited_at = datetime.utcnow()
        self.recalculate_stats()
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "property_code": self.property_code,
            "faq_key": self.faq_key,
            "total_count": self.total_count,
            "approved_count": self.approved_count,
            "edited_count": self.edited_count,
            "approval_rate": round(self.approval_rate, 4),
            "eligible_for_auto_send": self.eligible_for_auto_send,
            "last_approved_at": self.last_approved_at.isoformat() if self.last_approved_at else None,
            "last_edited_at": self.last_edited_at.isoformat() if self.last_edited_at else None,
        }
