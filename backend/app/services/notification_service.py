# backend/app/services/notification_service.py
"""
In-App Notification Service

알림 생성 및 관리 서비스
다른 서비스에서 이 서비스를 호출하여 알림 생성
"""
from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.models.notification import Notification, NotificationType, NotificationPriority
from app.repositories.notification_repository import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: Session, enable_push: bool = True):
        self.db = db
        self.repo = NotificationRepository(db)
        self._enable_push = enable_push
        self._push_service = None  # Lazy loading
    
    @property
    def push_service(self):
        """PushService lazy loading (import cycle 방지)"""
        if self._push_service is None and self._enable_push:
            try:
                from app.services.push_service import PushService
                self._push_service = PushService(self.db)
            except Exception as e:
                logger.warning(f"Failed to initialize PushService: {e}")
        return self._push_service

    # ------------------------------------------------------------------
    # 알림 생성 헬퍼 메서드
    # ------------------------------------------------------------------

    def create_safety_alert(
        self,
        *,
        property_code: str,
        guest_name: str,
        message_preview: str,
        airbnb_thread_id: str,
    ) -> Optional[Notification]:
        """🔴 안전 알림 생성 (safety_status = block) - 중복 체크 + Push"""
        # 중복 체크: 같은 thread에 대해 30분 내 동일 알림 있으면 스킵
        if self.repo.exists_recent(
            type=NotificationType.safety_alert.value,
            airbnb_thread_id=airbnb_thread_id,
            minutes=30,
        ):
            logger.debug(f"Skipping duplicate safety_alert for {airbnb_thread_id}")
            return None
        
        logger.info(f"Creating safety alert for {property_code} - {guest_name}")
        
        notification = self.repo.create(
            type=NotificationType.safety_alert.value,
            priority=NotificationPriority.critical.value,
            title="🔴 안전 알림 - 즉시 확인 필요",
            body=f"{property_code} {guest_name}: {message_preview[:150]}",
            link_type="conversation",
            link_id=airbnb_thread_id,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )
        
        # 🔔 Browser Push 전송 (critical이므로)
        if notification and self.push_service:
            try:
                self.push_service.send_critical_alert(
                    property_code=property_code,
                    guest_name=guest_name,
                    message_preview=message_preview,
                    airbnb_thread_id=airbnb_thread_id,
                )
            except Exception as e:
                logger.warning(f"Failed to send push for safety_alert: {e}")
        
        return notification

    def create_unanswered_warning(
        self,
        *,
        property_code: str,
        guest_name: str,
        minutes_unanswered: int,
        airbnb_thread_id: str,
    ) -> Optional[Notification]:
        """🟡 미응답 경고 생성 - 중복 체크 + Push"""
        # 중복 체크: 같은 thread에 대해 30분 내 동일 알림 있으면 스킵
        if self.repo.exists_recent(
            type=NotificationType.unanswered_warning.value,
            airbnb_thread_id=airbnb_thread_id,
            minutes=30,
        ):
            logger.debug(f"Skipping duplicate unanswered_warning for {airbnb_thread_id}")
            return None
        
        logger.info(f"Creating unanswered warning for {property_code} - {guest_name} ({minutes_unanswered}분)")
        
        notification = self.repo.create(
            type=NotificationType.unanswered_warning.value,
            priority=NotificationPriority.high.value,
            title=f"🟡 미응답 {minutes_unanswered}분 경과",
            body=f"{property_code} {guest_name}님 응답 대기 중",
            link_type="conversation",
            link_id=airbnb_thread_id,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )
        
        # 🔔 Browser Push 전송
        if notification and self.push_service:
            try:
                self.push_service.send_unanswered_warning(
                    property_code=property_code,
                    guest_name=guest_name,
                    minutes=minutes_unanswered,
                    airbnb_thread_id=airbnb_thread_id,
                )
            except Exception as e:
                logger.warning(f"Failed to send push for unanswered_warning: {e}")
        
        return notification

    def create_booking_confirmed(
        self,
        *,
        property_code: str,
        guest_name: str,
        checkin_date: str,
        reservation_code: Optional[str] = None,
        airbnb_thread_id: Optional[str] = None,
    ) -> Optional[Notification]:
        """✅ 예약 확정 알림 생성 (중복 체크)"""
        # 중복 체크: 같은 thread에 대해 24시간 내 동일 알림 있으면 스킵
        if airbnb_thread_id and self.repo.exists_recent(
            type=NotificationType.booking_confirmed.value,
            airbnb_thread_id=airbnb_thread_id,
            minutes=1440,  # 24시간
        ):
            logger.debug(f"Skipping duplicate booking_confirmed for {airbnb_thread_id}")
            return None
        
        logger.info(f"Creating booking confirmed notification for {property_code} - {guest_name}")
        
        return self.repo.create(
            type=NotificationType.booking_confirmed.value,
            priority=NotificationPriority.normal.value,
            title="✅ 예약 확정",
            body=f"{guest_name}님 {checkin_date} 체크인",
            link_type="reservation",
            link_id=reservation_code,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )

    def create_booking_cancelled(
        self,
        *,
        property_code: str,
        guest_name: str,
        reservation_code: str,
        airbnb_thread_id: Optional[str] = None,
    ) -> Optional[Notification]:
        """⚠️ 예약 취소 알림 생성 - 중복 체크"""
        # reservation_code가 없으면 중복 체크 불가 → 스킵
        if not reservation_code:
            logger.warning("Skipping booking_cancelled notification: no reservation_code")
            return None
        
        # 중복 체크: 같은 reservation_code에 대해 24시간 내 동일 알림 있으면 스킵
        if self.repo.exists_recent(
            type=NotificationType.booking_cancelled.value,
            reservation_code=reservation_code,
            minutes=1440,  # 24시간
        ):
            logger.debug(f"Skipping duplicate booking_cancelled for {reservation_code}")
            return None
        
        logger.info(f"Creating booking cancelled notification for {property_code} - {guest_name}")
        
        return self.repo.create(
            type=NotificationType.booking_cancelled.value,
            priority=NotificationPriority.high.value,
            title="⚠️ 예약 취소됨",
            body=f"{property_code} {guest_name}님 ({reservation_code})",
            link_type="reservation",
            link_id=reservation_code,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )

    def create_booking_rtb(
        self,
        *,
        property_code: str,
        guest_name: str,
        checkin_date: str,
        checkout_date: str,
        airbnb_thread_id: str,
    ) -> Optional[Notification]:
        """📩 예약 요청(RTB) 알림 생성 - 중복 체크 + Push"""
        # 중복 체크: 24시간 내 동일 알림 있으면 스킵
        if self.repo.exists_recent(
            type=NotificationType.booking_rtb.value,
            airbnb_thread_id=airbnb_thread_id,
            minutes=1440,  # 24시간
        ):
            logger.debug(f"Skipping duplicate booking_rtb for {airbnb_thread_id}")
            return None
        
        logger.info(f"Creating RTB notification for {property_code} - {guest_name}")
        
        notification = self.repo.create(
            type=NotificationType.booking_rtb.value,
            priority=NotificationPriority.high.value,
            title="📩 예약 요청 - 승인 필요",
            body=f"{property_code} {guest_name}님 {checkin_date}~{checkout_date}",
            link_type="reservation",
            link_id=airbnb_thread_id,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )
        
        # 🔔 Browser Push 전송 (high priority)
        if notification and self.push_service:
            try:
                self.push_service.send_booking_rtb(
                    property_code=property_code,
                    guest_name=guest_name,
                    checkin_date=checkin_date,
                    airbnb_thread_id=airbnb_thread_id,
                )
            except Exception as e:
                logger.warning(f"Failed to send push for booking_rtb: {e}")
        
        return notification

    def create_new_guest_message(
        self,
        *,
        property_code: str,
        guest_name: str,
        message_preview: str,
        airbnb_thread_id: str,
    ) -> Optional[Notification]:
        """💬 새 게스트 메시지 알림 생성 - 중복 체크"""
        # 중복 체크: 같은 thread에 대해 5분 내 동일 알림 있으면 스킵
        if self.repo.exists_recent(
            type=NotificationType.new_guest_message.value,
            airbnb_thread_id=airbnb_thread_id,
            minutes=5,
        ):
            logger.debug(f"Skipping duplicate new_guest_message for {airbnb_thread_id}")
            return None
        
        logger.info(f"Creating new message notification for {property_code} - {guest_name}")
        
        return self.repo.create(
            type=NotificationType.new_guest_message.value,
            priority=NotificationPriority.normal.value,
            title=f"💬 {guest_name}님의 새 메시지",
            body=f"{property_code}: {message_preview[:100]}",
            link_type="conversation",
            link_id=airbnb_thread_id,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )

    def create_oc_reminder(
        self,
        *,
        oc_count: int,
        oc_items: List[Dict[str, Any]],
    ) -> Optional[Notification]:
        """📋 당일 OC 리마인더 생성 - 하루 1회"""
        # 중복 체크: 오늘 이미 알림 있으면 스킵 (24시간 = 1440분)
        if self.repo.exists_recent(
            type=NotificationType.oc_reminder.value,
            minutes=1440,
        ):
            logger.debug("Skipping duplicate oc_reminder (already sent today)")
            return None
        
        logger.info(f"Creating OC reminder for {oc_count} items")
        
        # 요약 생성
        summaries = []
        for oc in oc_items[:3]:  # 최대 3개만 표시
            summaries.append(f"• {oc.get('property_code', '')} - {oc.get('action', '')[:30]}")
        
        body = "\n".join(summaries)
        if oc_count > 3:
            body += f"\n... 외 {oc_count - 3}건"
        
        return self.repo.create(
            type=NotificationType.oc_reminder.value,
            priority=NotificationPriority.normal.value,
            title=f"📋 오늘 처리할 약속 {oc_count}건",
            body=body,
            link_type="staff_notification",
            link_id=None,
        )

    def create_same_day_checkin(
        self,
        *,
        property_code: str,
        guest_name: str,
        reservation_code: Optional[str] = None,
        airbnb_thread_id: Optional[str] = None,
    ) -> Optional[Notification]:
        """🏃 당일 체크인 예약 알림 - 중복 체크"""
        # 중복 체크: 같은 예약에 대해 24시간 내 동일 알림 있으면 스킵
        if airbnb_thread_id and self.repo.exists_recent(
            type=NotificationType.same_day_checkin.value,
            airbnb_thread_id=airbnb_thread_id,
            minutes=1440,
        ):
            logger.debug(f"Skipping duplicate same_day_checkin for {airbnb_thread_id}")
            return None
        
        logger.info(f"Creating same day checkin notification for {property_code} - {guest_name}")
        
        return self.repo.create(
            type=NotificationType.same_day_checkin.value,
            priority=NotificationPriority.high.value,
            title="🏃 당일 체크인 예약!",
            body=f"{property_code} {guest_name}님 오늘 체크인",
            link_type="reservation",
            link_id=reservation_code,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )

    def create_overbooking_alert(
        self,
        *,
        property_code: str,
        checkin_date: str,
        reservation_count: int,
        guest_names: List[str],
    ) -> Optional[Notification]:
        """🚨 오버부킹 의심 알림 - 중복 체크"""
        # 중복 체크: 같은 property_code + checkin_date에 대해 24시간 내 동일 알림 있으면 스킵
        # airbnb_thread_id 대신 property_code + checkin_date 조합으로 체크
        check_key = f"{property_code}_{checkin_date}"
        if self.repo.exists_recent(
            type=NotificationType.overbooking_alert.value,
            property_code=property_code,
            minutes=1440,
        ):
            logger.debug(f"Skipping duplicate overbooking_alert for {check_key}")
            return None
        
        logger.warning(f"Creating overbooking alert for {property_code} - {checkin_date} ({reservation_count}건)")
        
        guest_list = ", ".join(guest_names[:3])
        if len(guest_names) > 3:
            guest_list += f" 외 {len(guest_names) - 3}명"
        
        return self.repo.create(
            type=NotificationType.overbooking_alert.value,
            priority=NotificationPriority.critical.value,
            title=f"🚨 오버부킹 의심 - {property_code}",
            body=f"{checkin_date} 체크인 예약 {reservation_count}건 감지\n게스트: {guest_list}",
            link_type="reservation",
            link_id=None,
            property_code=property_code,
            guest_name=None,
            airbnb_thread_id=None,
        )

    def create_complaint_alert(
        self,
        *,
        property_code: str,
        guest_name: str,
        category: str,
        category_label: str,
        severity: str,
        description: str,
        airbnb_thread_id: str,
        conversation_id: Optional[str] = None,
    ) -> Optional[Notification]:
        """🔴 게스트 불만/문제 감지 알림 - 중복 체크 + Push
        
        severity에 따라 priority 결정:
        - critical → critical (즉시 확인)
        - high → high (주의)
        - medium/low → normal (정보)
        """
        # 중복 체크: 같은 thread + category에 대해 1시간 내 동일 알림 있으면 스킵
        if self.repo.exists_recent(
            type=NotificationType.complaint_alert.value,
            airbnb_thread_id=airbnb_thread_id,
            minutes=60,
        ):
            logger.debug(f"Skipping duplicate complaint_alert for {airbnb_thread_id}")
            return None
        
        # severity에 따른 priority 및 아이콘 결정
        if severity == "critical":
            priority = NotificationPriority.critical.value
            icon = "🚨"
        elif severity == "high":
            priority = NotificationPriority.high.value
            icon = "🔴"
        else:
            priority = NotificationPriority.normal.value
            icon = "⚠️"
        
        logger.info(f"Creating complaint alert for {property_code} - {guest_name} ({category})")
        
        notification = self.repo.create(
            type=NotificationType.complaint_alert.value,
            priority=priority,
            title=f"{icon} {category_label} - {property_code}",
            body=f"{guest_name}님: {description[:150]}",
            link_type="conversation",
            link_id=airbnb_thread_id,
            property_code=property_code,
            guest_name=guest_name,
            airbnb_thread_id=airbnb_thread_id,
        )
        
        # 🔔 Browser Push 전송 (high/critical일 때)
        if notification and self.push_service and severity in ["critical", "high"]:
            try:
                self.push_service.send_complaint_alert(
                    property_code=property_code,
                    guest_name=guest_name,
                    category_label=category_label,
                    severity=severity,
                    airbnb_thread_id=airbnb_thread_id,
                )
            except Exception as e:
                logger.warning(f"Failed to send push for complaint_alert: {e}")
        
        return notification

    # ------------------------------------------------------------------
    # 일반 메서드
    # ------------------------------------------------------------------

    def create_notification(
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
        """범용 알림 생성"""
        return self.repo.create(
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

    def get_notifications(
        self,
        *,
        unread_only: bool = False,
        type_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Notification]:
        """알림 목록 조회"""
        return self.repo.list_notifications(
            unread_only=unread_only,
            type_filter=type_filter,
            limit=limit,
        )

    def get_unread_count(self) -> int:
        """미읽음 알림 개수"""
        return self.repo.get_unread_count()

    def get_unread_summary(self) -> Dict[str, Any]:
        """미읽음 알림 요약 (Bell 뱃지용)"""
        by_priority = self.repo.get_unread_by_priority()
        total = sum(by_priority.values())
        
        return {
            "total": total,
            "critical": by_priority.get("critical", 0),
            "high": by_priority.get("high", 0),
            "normal": by_priority.get("normal", 0),
            "low": by_priority.get("low", 0),
        }

    def mark_as_read(self, notification_id: UUID) -> Optional[Notification]:
        """알림 읽음 처리"""
        return self.repo.mark_as_read(notification_id)

    def mark_all_as_read(self) -> int:
        """모든 알림 읽음 처리"""
        return self.repo.mark_all_as_read()

    def delete_notification(self, notification_id: UUID) -> bool:
        """개별 알림 삭제"""
        return self.repo.delete(notification_id)

    def delete_all_notifications(self) -> int:
        """모든 알림 삭제"""
        return self.repo.delete_all()
