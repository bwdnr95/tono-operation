from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.staff_notification_repository import StaffNotificationRepository
from app.domain.models.staff_notification_record import StaffNotificationRecord


# ----------------------------
# DB Session
# ----------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------
# Pydantic Models
# ----------------------------

class StaffNotificationUpdate(BaseModel):
    """
    PATCH 요청 바디
    { "status": "RESOLVED" }
    """
    status: str  # "OPEN" | "IN_PROGRESS" | "RESOLVED"


class StaffNotificationOut(BaseModel):
    id: int
    message_id: int
    property_code: Optional[str]
    ota: Optional[str]
    guest_name: Optional[str]
    checkin_date: Optional[str]
    checkout_date: Optional[str] = None
    message_summary: str
    follow_up_actions: List[str]
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        orm_mode = True


router = APIRouter(
    prefix="/staff-notifications",
    tags=["staff_notifications"],
)


# ----------------------------
# PATCH: Update Notification Status
# ----------------------------

@router.patch(
    "/{notification_id}",
    response_model=StaffNotificationOut,
    status_code=status.HTTP_200_OK,
)
def update_staff_notification_status(
    notification_id: int,
    update: StaffNotificationUpdate,   # ← JSON Body "{status: 'RESOLVED'}"
    db: Session = Depends(get_db),
):
    repo = StaffNotificationRepository(db)

    rec: StaffNotificationRecord | None = repo.get(notification_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    new_status = update.status.upper()
    if new_status not in ("OPEN", "IN_PROGRESS", "RESOLVED"):
        raise HTTPException(status_code=400, detail="Invalid status value")

    now = datetime.utcnow()

    rec.status = new_status
    rec.updated_at = now
    rec.resolved_at = now if new_status == "RESOLVED" else None

    db.add(rec)
    db.commit()
    db.refresh(rec)

    return StaffNotificationOut(
        id=rec.id,
        message_id=rec.message_id,
        property_code=rec.property_code,
        ota=rec.ota,
        guest_name=rec.guest_name,
        checkin_date=str(rec.checkin_date) if rec.checkin_date else None,
        checkout_date=str(rec.checkout_date) if getattr(rec, "checkout_date", None) else None,
        message_summary=rec.message_summary,
        follow_up_actions=rec.follow_up_actions or [],
        status=rec.status,
        created_at=rec.created_at,
        resolved_at=rec.resolved_at,
    )


# ----------------------------
# GET: List Notifications
# ----------------------------

@router.get("", response_model=List[StaffNotificationOut])
def list_staff_notifications(
    unresolved_only: bool = Query(False, description="true이면 RESOLVED 제외"),
    property_code: Optional[str] = Query(None),
    ota: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    repo = StaffNotificationRepository(db)

    # ✅ 레포에는 status를 단일 값으로만 넘긴다 (또는 None)
    # unresolved_only 기능은 파이썬 레벨에서 처리
    records = repo.list(
        status=None,               # ← 여기! 더 이상 ['OPEN','IN_PROGRESS'] 같은 리스트 안 넘김
        property_code=property_code,
        ota=ota,
        limit=limit,
    )

    if unresolved_only:
        # ✅ RESOLVED 아닌 것만 남기기
        records = [r for r in records if r.status != "RESOLVED"]

    return [
        StaffNotificationOut(
            id=r.id,
            message_id=r.message_id,
            property_code=r.property_code,
            ota=r.ota,
            guest_name=r.guest_name,
            checkin_date=str(r.checkin_date) if r.checkin_date else None,
            checkout_date=str(r.checkout_date) if getattr(r, "checkout_date", None) else None,
            message_summary=r.message_summary,
            follow_up_actions=r.follow_up_actions or [],
            status=r.status,
            created_at=r.created_at,
            resolved_at=r.resolved_at,
        )
        for r in records
    ]


# ----------------------------
# GET: Single Notification
# ----------------------------

@router.get("/{notification_id}", response_model=StaffNotificationOut)
def get_staff_notification(
    notification_id: int,
    db: Session = Depends(get_db),
):
    repo = StaffNotificationRepository(db)
    record = repo.get(notification_id)
    if not record:
        raise HTTPException(status_code=404, detail="Notification not found")

    return StaffNotificationOut(
        id=record.id,
        message_id=record.message_id,
        property_code=record.property_code,
        ota=record.ota,
        guest_name=record.guest_name,
        checkin_date=str(record.checkin_date) if record.checkin_date else None,
        checkout_date=str(record.checkout_date) if getattr(record, "checkout_date", None) else None,
        message_summary=record.message_summary,
        follow_up_actions=record.follow_up_actions or [],
        status=record.status,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
    )
