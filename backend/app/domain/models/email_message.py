from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, UniqueConstraint

from app.db.base import Base


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("gmail_message_id", name="uq_email_messages_gmail_message_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Gmail 쪽 메타
    gmail_message_id = Column(String(255), nullable=False)
    gmail_thread_id = Column(String(128), nullable=True)

    # 발신/제목/본문
    from_addr = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=True)
    text_body = Column(Text, nullable=True)
    html_body = Column(Text, nullable=True)

    # Airbnb/TONO 쪽 메타
    guest_name = Column(String(255), nullable=True)
    listing_name = Column(String(255), nullable=True)
    reservation_code = Column(String(64), nullable=True)
    intent = Column(String(50), nullable=True)   # 도메인 Intent 이름
    source = Column(String(50), nullable=False)  # 예: "airbnb-gmail"

    raw_json = Column(JSON, nullable=True)

    received_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)