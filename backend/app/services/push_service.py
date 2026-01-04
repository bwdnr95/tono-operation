# backend/app/services/push_service.py
"""
Web Push Notification Service

Browser Push Notification을 전송하는 서비스.
pywebpush 라이브러리 사용.

사용법:
    push_service = PushService(db)
    push_service.send_to_all(
        title="🔴 안전 알림",
        body="2Y2-1 채은님: 가스 냄새가...",
        url="/inbox?thread=xxx"
    )

환경변수 필요:
    VAPID_PUBLIC_KEY: VAPID 공개키
    VAPID_PRIVATE_KEY: VAPID 비밀키
    VAPID_CLAIMS_EMAIL: mailto:your@email.com
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories.push_subscription_repository import PushSubscriptionRepository

logger = logging.getLogger(__name__)


@dataclass
class PushResult:
    """Push 전송 결과"""
    success_count: int
    failure_count: int
    failed_endpoints: List[str]


class PushService:
    """Web Push 알림 전송 서비스"""
    
    def __init__(self, db: Session):
        self.db = db
        self.repo = PushSubscriptionRepository(db)
        
        # VAPID 설정
        self.vapid_public_key = os.getenv("VAPID_PUBLIC_KEY", "")
        self.vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "")
        self.vapid_claims_email = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@tono.co.kr")
    
    def get_vapid_public_key(self) -> str:
        """프론트엔드에서 사용할 VAPID 공개키 반환"""
        return self.vapid_public_key
    
    def subscribe(
        self,
        *,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: Optional[str] = None,
    ) -> bool:
        """Push 구독 등록"""
        try:
            self.repo.upsert(
                endpoint=endpoint,
                p256dh_key=p256dh_key,
                auth_key=auth_key,
                user_agent=user_agent,
            )
            logger.info(f"Push subscription registered: {endpoint[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to register push subscription: {e}")
            return False
    
    def unsubscribe(self, endpoint: str) -> bool:
        """Push 구독 해제"""
        try:
            result = self.repo.deactivate(endpoint)
            if result:
                logger.info(f"Push subscription deactivated: {endpoint[:50]}...")
            return result
        except Exception as e:
            logger.error(f"Failed to deactivate push subscription: {e}")
            return False
    
    def send_to_all(
        self,
        *,
        title: str,
        body: str,
        url: Optional[str] = None,
        icon: str = "/tono-icon.png",
        tag: Optional[str] = None,
        priority: str = "normal",
    ) -> PushResult:
        """모든 활성 구독자에게 Push 전송"""
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            logger.error("pywebpush not installed. Run: pip install pywebpush")
            return PushResult(success_count=0, failure_count=0, failed_endpoints=[])
        
        if not self.vapid_private_key:
            logger.warning("VAPID_PRIVATE_KEY not configured, skipping push")
            return PushResult(success_count=0, failure_count=0, failed_endpoints=[])
        
        subscriptions = self.repo.get_all_active()
        
        if not subscriptions:
            logger.debug("No active push subscriptions")
            return PushResult(success_count=0, failure_count=0, failed_endpoints=[])
        
        # Push 페이로드
        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": icon,
            "url": url,
            "tag": tag,
            "priority": priority,
            "timestamp": int(__import__("time").time() * 1000),
        })
        
        # VAPID 클레임
        vapid_claims = {
            "sub": self.vapid_claims_email,
        }
        
        success_count = 0
        failure_count = 0
        failed_endpoints = []
        
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info=sub.to_webpush_dict(),
                    data=payload,
                    vapid_private_key=self.vapid_private_key,
                    vapid_claims=vapid_claims,
                )
                success_count += 1
                logger.debug(f"Push sent to {sub.endpoint[:50]}...")
                
            except WebPushException as e:
                failure_count += 1
                failed_endpoints.append(sub.endpoint)
                logger.warning(f"Push failed for {sub.endpoint[:50]}...: {e}")
                
                # 410 Gone = 구독 만료 → 비활성화
                if e.response and e.response.status_code == 410:
                    self.repo.deactivate(sub.endpoint)
                    logger.info(f"Deactivated expired subscription: {sub.endpoint[:50]}...")
                    
            except Exception as e:
                failure_count += 1
                failed_endpoints.append(sub.endpoint)
                logger.error(f"Unexpected error sending push: {e}")
        
        logger.info(f"Push sent: {success_count} success, {failure_count} failed")
        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failed_endpoints=failed_endpoints,
        )
    
    def send_critical_alert(
        self,
        *,
        property_code: str,
        guest_name: str,
        message_preview: str,
        airbnb_thread_id: str,
    ) -> PushResult:
        """🔴 Safety Alert Push 전송"""
        return self.send_to_all(
            title="🔴 안전 알림 - 즉시 확인 필요",
            body=f"{property_code} {guest_name}: {message_preview[:100]}",
            url=f"/inbox?thread={airbnb_thread_id}",
            tag=f"safety-{airbnb_thread_id}",
            priority="high",
        )
    
    def send_booking_rtb(
        self,
        *,
        property_code: str,
        guest_name: str,
        checkin_date: str,
        airbnb_thread_id: str,
    ) -> PushResult:
        """📩 예약 요청 Push 전송"""
        return self.send_to_all(
            title="📩 예약 요청 - 승인 필요",
            body=f"{property_code} {guest_name}님 {checkin_date} 체크인",
            url=f"/booking-requests?thread={airbnb_thread_id}",
            tag=f"rtb-{airbnb_thread_id}",
            priority="high",
        )
    
    def send_unanswered_warning(
        self,
        *,
        property_code: str,
        guest_name: str,
        minutes: int,
        airbnb_thread_id: str,
    ) -> PushResult:
        """🟡 미응답 경고 Push 전송"""
        return self.send_to_all(
            title=f"🟡 미응답 {minutes}분 경과",
            body=f"{property_code} {guest_name}님 응답 대기 중",
            url=f"/inbox?thread={airbnb_thread_id}",
            tag=f"unanswered-{airbnb_thread_id}",
            priority="normal",
        )
    
    def send_complaint_alert(
        self,
        *,
        property_code: str,
        guest_name: str,
        category_label: str,
        severity: str,
        airbnb_thread_id: str,
    ) -> PushResult:
        """🔴 게스트 불만/문제 감지 Push 전송"""
        # severity에 따른 아이콘
        if severity == "critical":
            icon_emoji = "🚨"
            priority = "high"
        elif severity == "high":
            icon_emoji = "🔴"
            priority = "high"
        else:
            icon_emoji = "⚠️"
            priority = "normal"
        
        return self.send_to_all(
            title=f"{icon_emoji} {category_label} - {property_code}",
            body=f"{guest_name}님이 문제를 신고했습니다",
            url=f"/inbox?thread={airbnb_thread_id}",
            tag=f"complaint-{airbnb_thread_id}",
            priority=priority,
        )
