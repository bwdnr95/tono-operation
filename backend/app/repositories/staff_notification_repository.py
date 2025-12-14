# backend/app/repositories/staff_notification_repository.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.domain.models.staff_notification_record import StaffNotificationRecord
from app.domain.models.staff_notification import StaffNotification


class StaffNotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 기본 CRUD
    # ------------------------------------------------------------------

    def get(self, notification_id: int) -> Optional[StaffNotificationRecord]:
        return self.db.query(StaffNotificationRecord).get(notification_id)

    def create_from_domain(self, domain: StaffNotification, message_id: int) -> StaffNotificationRecord:
        record = StaffNotificationRecord(
            message_id=message_id,
            property_code=domain.property_code,
            ota=domain.ota,
            guest_name=domain.guest_name,
            checkin_date=domain.checkin_date,
            checkout_date=domain.checkout_date,
            message_summary=domain.message_summary,
            follow_up_actions=domain.follow_up_actions,
            status=domain.status,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # 리스트 조회
    # ------------------------------------------------------------------

    def list(
        self,
        *,
        status: Optional[str] = None,
        property_code: Optional[str] = None,
        ota: Optional[str] = None,
        limit: int = 50,
    ) -> List[StaffNotificationRecord]:
        q = self.db.query(StaffNotificationRecord).filter(
            StaffNotificationRecord.is_active.is_(True)
        )

        if status:
            q = q.filter(StaffNotificationRecord.status == status)

        if property_code:
            q = q.filter(StaffNotificationRecord.property_code == property_code)

        if ota:
            q = q.filter(StaffNotificationRecord.ota == ota)

        q = q.order_by(StaffNotificationRecord.created_at.desc())
        if limit:
            q = q.limit(limit)

        return q.all()

    def list_open(self, property_code: Optional[str] = None) -> List[StaffNotificationRecord]:
        return self.list(status="OPEN", property_code=property_code)

    # ------------------------------------------------------------------
    # 상태 변경
    # ------------------------------------------------------------------

    def mark_done(self, notification_id: int, resolved_by: str) -> Optional[StaffNotificationRecord]:
        rec = self.db.query(StaffNotificationRecord).get(notification_id)
        if not rec:
            return None
        rec.status = "DONE"
        rec.resolved_by = resolved_by
        self.db.commit()
        self.db.refresh(rec)
        return rec
