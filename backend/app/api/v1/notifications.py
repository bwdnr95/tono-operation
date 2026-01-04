"""
In-App Notification API 엔드포인트

- GET /notifications - 알림 목록
- GET /notifications/count - 미읽음 개수 (Bell 뱃지용)
- GET /notifications/summary - 우선순위별 미읽음 요약
- POST /notifications/{id}/read - 읽음 처리
- POST /notifications/read-all - 전체 읽음 처리
- DELETE /notifications/{id} - 개별 삭제
- DELETE /notifications - 전체 삭제
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ─────────────────────────────────────────────────────────────
# DTOs
# ─────────────────────────────────────────────────────────────

class NotificationDTO(BaseModel):
    id: str
    type: str
    priority: str
    title: str
    body: Optional[str] = None
    link_type: Optional[str] = None
    link_id: Optional[str] = None
    property_code: Optional[str] = None
    guest_name: Optional[str] = None
    airbnb_thread_id: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    notifications: List[NotificationDTO]
    total: int
    unread_count: int


class NotificationCountResponse(BaseModel):
    count: int


class NotificationSummaryResponse(BaseModel):
    total: int
    critical: int
    high: int
    normal: int
    low: int


class MarkReadResponse(BaseModel):
    success: bool
    notification_id: Optional[str] = None


class MarkAllReadResponse(BaseModel):
    success: bool
    count: int


class DeleteResponse(BaseModel):
    success: bool
    deleted_count: int = 0


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("", response_model=NotificationListResponse)
def get_notifications(
    unread_only: bool = Query(False, description="미읽음만 조회"),
    type_filter: Optional[str] = Query(None, description="알림 유형 필터"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """알림 목록 조회"""
    service = NotificationService(db)
    
    notifications = service.get_notifications(
        unread_only=unread_only,
        type_filter=type_filter,
        limit=limit,
    )
    
    unread_count = service.get_unread_count()
    
    return NotificationListResponse(
        notifications=[
            NotificationDTO(
                id=str(n.id),
                type=n.type,
                priority=n.priority,
                title=n.title,
                body=n.body,
                link_type=n.link_type,
                link_id=n.link_id,
                property_code=n.property_code,
                guest_name=n.guest_name,
                airbnb_thread_id=n.airbnb_thread_id,
                is_read=n.is_read,
                read_at=n.read_at,
                created_at=n.created_at,
            )
            for n in notifications
        ],
        total=len(notifications),
        unread_count=unread_count,
    )


@router.get("/count", response_model=NotificationCountResponse)
def get_notification_count(db: Session = Depends(get_db)):
    """미읽음 알림 개수 (Bell 뱃지용)"""
    service = NotificationService(db)
    count = service.get_unread_count()
    
    return NotificationCountResponse(count=count)


@router.get("/summary", response_model=NotificationSummaryResponse)
def get_notification_summary(db: Session = Depends(get_db)):
    """우선순위별 미읽음 요약"""
    service = NotificationService(db)
    summary = service.get_unread_summary()
    
    return NotificationSummaryResponse(**summary)


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
def mark_notification_as_read(
    notification_id: str,
    db: Session = Depends(get_db),
):
    """특정 알림 읽음 처리"""
    service = NotificationService(db)
    
    try:
        uuid_id = UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification ID format")
    
    notification = service.mark_as_read(uuid_id)
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return MarkReadResponse(success=True, notification_id=str(notification.id))


@router.post("/read-all", response_model=MarkAllReadResponse)
def mark_all_notifications_as_read(db: Session = Depends(get_db)):
    """모든 알림 읽음 처리"""
    service = NotificationService(db)
    count = service.mark_all_as_read()
    
    return MarkAllReadResponse(success=True, count=count)


@router.delete("/{notification_id}", response_model=DeleteResponse)
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
):
    """특정 알림 삭제"""
    service = NotificationService(db)
    
    try:
        uuid_id = UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification ID format")
    
    success = service.delete_notification(uuid_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return DeleteResponse(success=True, deleted_count=1)


@router.delete("", response_model=DeleteResponse)
def delete_all_notifications(db: Session = Depends(get_db)):
    """모든 알림 삭제"""
    service = NotificationService(db)
    count = service.delete_all_notifications()
    
    return DeleteResponse(success=True, deleted_count=count)
