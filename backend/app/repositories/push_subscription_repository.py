# backend/app/repositories/push_subscription_repository.py
"""
Push Subscription Repository
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.models.push_subscription import PushSubscription


class PushSubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: Optional[str] = None,
    ) -> PushSubscription:
        """새 구독 생성"""
        subscription = PushSubscription(
            endpoint=endpoint,
            p256dh_key=p256dh_key,
            auth_key=auth_key,
            user_agent=user_agent,
        )
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def get_by_endpoint(self, endpoint: str) -> Optional[PushSubscription]:
        """엔드포인트로 구독 조회"""
        stmt = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all_active(self) -> List[PushSubscription]:
        """활성 구독 전체 조회"""
        stmt = (
            select(PushSubscription)
            .where(PushSubscription.is_active == True)
            .order_by(PushSubscription.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def upsert(
        self,
        *,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: Optional[str] = None,
    ) -> PushSubscription:
        """구독 생성 또는 업데이트 (endpoint 기준)"""
        existing = self.get_by_endpoint(endpoint)
        
        if existing:
            existing.p256dh_key = p256dh_key
            existing.auth_key = auth_key
            existing.user_agent = user_agent
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing
        
        return self.create(
            endpoint=endpoint,
            p256dh_key=p256dh_key,
            auth_key=auth_key,
            user_agent=user_agent,
        )

    def deactivate(self, endpoint: str) -> bool:
        """구독 비활성화"""
        existing = self.get_by_endpoint(endpoint)
        if existing:
            existing.is_active = False
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            return True
        return False

    def delete(self, endpoint: str) -> bool:
        """구독 삭제"""
        existing = self.get_by_endpoint(endpoint)
        if existing:
            self.db.delete(existing)
            self.db.commit()
            return True
        return False

    def delete_inactive_old(self, days: int = 30) -> int:
        """오래된 비활성 구독 삭제"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        stmt = (
            select(PushSubscription)
            .where(PushSubscription.is_active == False)
            .where(PushSubscription.updated_at < cutoff)
        )
        old_subs = list(self.db.execute(stmt).scalars().all())
        
        for sub in old_subs:
            self.db.delete(sub)
        
        self.db.commit()
        return len(old_subs)
