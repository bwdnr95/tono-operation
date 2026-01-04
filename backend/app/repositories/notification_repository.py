# backend/app/repositories/notification_repository.py
"""
In-App Notification Repository
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.domain.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 중복 체크
    # ------------------------------------------------------------------

    def exists_recent(
        self,
        *,
        type: str,
        airbnb_thread_id: Optional[str] = None,
        reservation_code: Optional[str] = None,
        property_code: Optional[str] = None,
        minutes: int = 60,
    ) -> bool:
        """
        최근 N분 내에 동일한 알림이 있는지 확인
        
        NOTE: is_deleted 상관없이 체크함.
        삭제된 알림도 중복으로 간주해야 함.
        (사용자가 삭제해도 같은 메일 재처리 시 다시 생성되면 안 됨)
        """
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        
        # is_deleted 조건 없음 (삭제된 알림도 중복 체크 대상)
        stmt = select(Notification).where(
            Notification.type == type,
            Notification.created_at >= cutoff,
        )
        
        if airbnb_thread_id:
            stmt = stmt.where(Notification.airbnb_thread_id == airbnb_thread_id)
        
        if reservation_code:
            stmt = stmt.where(Notification.link_id == reservation_code)
        
        if property_code:
            stmt = stmt.where(Notification.property_code == property_code)
        
        result = self.db.execute(stmt).scalar_one_or_none()
        return result is not None

    # ------------------------------------------------------------------
    # 생성
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        type: str,
        priority: str,
        title: str,
        body: Optional[str] = None,
        link_type: Optional[str] = None,
        link_id: Optional[str] = None,
        property_code: Optional[str] = None,
        guest_name: Optional[str] = None,
        airbnb_thread_id: Optional[str] = None,
    ) -> Notification:
        notification = Notification(
            type=type,
            priority=priority,
            title=title,
            body=body,
            link_type=link_type,
            link_id=link_id,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------

    def get_by_id(self, notification_id: UUID) -> Optional[Notification]:
        stmt = select(Notification).where(Notification.id == notification_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_notifications(
        self,
        *,
        unread_only: bool = False,
        type_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Notification]:
        stmt = select(Notification).where(Notification.is_deleted == False)
        
        if unread_only:
            stmt = stmt.where(Notification.is_read == False)
        
        if type_filter:
            stmt = stmt.where(Notification.type == type_filter)
        
        if priority_filter:
            stmt = stmt.where(Notification.priority == priority_filter)
        
        stmt = stmt.order_by(desc(Notification.created_at))
        stmt = stmt.limit(limit).offset(offset)
        
        return list(self.db.execute(stmt).scalars().all())

    def get_unread_count(self) -> int:
        stmt = select(func.count(Notification.id)).where(
            Notification.is_read == False,
            Notification.is_deleted == False,
        )
        return self.db.execute(stmt).scalar() or 0

    def get_unread_by_priority(self) -> dict:
        """우선순위별 미읽음 개수 반환"""
        stmt = (
            select(Notification.priority, func.count(Notification.id))
            .where(Notification.is_read == False)
            .where(Notification.is_deleted == False)
            .group_by(Notification.priority)
        )
        results = self.db.execute(stmt).all()
        return {row[0]: row[1] for row in results}

    # ------------------------------------------------------------------
    # 상태 변경
    # ------------------------------------------------------------------

    def mark_as_read(self, notification_id: UUID) -> Optional[Notification]:
        notification = self.get_by_id(notification_id)
        if notification:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(notification)
        return notification

    def mark_all_as_read(self) -> int:
        """모든 미읽음 알림을 읽음 처리하고, 처리된 개수 반환"""
        stmt = (
            select(Notification)
            .where(Notification.is_read == False)
            .where(Notification.is_deleted == False)
        )
        notifications = list(self.db.execute(stmt).scalars().all())
        
        now = datetime.utcnow()
        for n in notifications:
            n.is_read = True
            n.read_at = now
        
        self.db.commit()
        return len(notifications)

    # ------------------------------------------------------------------
    # 삭제 (옵션)
    # ------------------------------------------------------------------

    def delete_old_notifications(self, days: int = 30) -> int:
        """N일 이상 지난 읽은 알림 삭제"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        stmt = (
            select(Notification)
            .where(Notification.is_read == True)
            .where(Notification.created_at < cutoff)
        )
        old_notifications = list(self.db.execute(stmt).scalars().all())
        
        for n in old_notifications:
            self.db.delete(n)
        
        self.db.commit()
        return len(old_notifications)

    def delete(self, notification_id: UUID) -> bool:
        """개별 알림 soft delete"""
        notification = self.get_by_id(notification_id)
        if notification:
            notification.is_deleted = True
            self.db.commit()
            return True
        return False

    def delete_all(self) -> int:
        """모든 알림 soft delete (삭제 안 된 것만)"""
        stmt = select(Notification).where(Notification.is_deleted == False)
        notifications = list(self.db.execute(stmt).scalars().all())
        count = len(notifications)
        
        for n in notifications:
            n.is_deleted = True
        
        self.db.commit()
        return count
