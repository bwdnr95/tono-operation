# backend/app/services/message_detail_service.py
from __future__ import annotations
from sqlalchemy.orm import Session

from app.repositories.messages import IncomingMessageRepository
from app.repositories.auto_reply_log_repository import AutoReplyLogRepository


class MessageDetailService:
    """
    메시지 상세 조회 + 최신 자동응답 로그(auto_reply_log) 결합 서비스
    """

    def __init__(self, db: Session):
        self.db = db
        self.msg_repo = IncomingMessageRepository(db)
        self.log_repo = AutoReplyLogRepository(db)

    def get_detail(self, message_id: int):
        """
        메시지 상세 + 자동응답 로그 조회
        """
        msg = self.msg_repo.get(message_id)
        if msg is None:
            return None

        latest_log = self.log_repo.get_latest_for_message(message_id)

        return {
            "message": msg,
            "latest_log": latest_log,
        }
