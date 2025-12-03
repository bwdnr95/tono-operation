from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MessageLog(Base):
    """
    지메일 → 파싱 → 인텐트 분류 결과를 저장하는 로그 테이블
    """
    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    source = Column(String(64), nullable=False)  # airbnb_gmail_new_message 등
    ota_reservation_id = Column(String(64), nullable=True, index=True)
    guest_name = Column(String(128), nullable=True)
    room_no = Column(String(32), nullable=True)

    raw_message = Column(Text, nullable=False)

    intent = Column(String(64), nullable=False)
    sub_intent = Column(String(64), nullable=True)
    confidence = Column(Float, nullable=False)

    auto_reply = Column(Boolean, default=False, nullable=False)
    need_human = Column(Boolean, default=True, nullable=False)
    reply_text = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)