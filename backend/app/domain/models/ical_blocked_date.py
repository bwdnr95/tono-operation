"""
iCal Blocked Date Model

iCal에서 파싱한 차단 날짜 저장
- Airbnb에서 직접 막은 날짜
- 다른 채널 예약으로 인한 차단
"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import String, Date, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IcalBlockedDate(Base):
    """
    iCal에서 파싱한 차단 날짜
    
    - property_code: 숙소 코드
    - blocked_date: 차단된 날짜
    - summary: iCal VEVENT의 SUMMARY (예: "Airbnb (Not available)")
    - uid: iCal VEVENT의 UID (중복 방지용)
    """
    
    __tablename__ = "ical_blocked_dates"
    
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    
    property_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    
    blocked_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    
    summary: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    
    uid: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    
    __table_args__ = (
        Index('idx_blocked_dates_property_date', 'property_code', 'blocked_date', unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<IcalBlockedDate {self.property_code} {self.blocked_date}>"
