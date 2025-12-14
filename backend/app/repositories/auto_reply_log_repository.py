from __future__ import annotations

from typing import List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.domain.models.auto_reply_log import AutoReplyLog
from app.domain.models.incoming_message import IncomingMessage


class AutoReplyLogRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 생성
    # ------------------------------------------------------------------

    def create_from_suggestion(
        self,
        *,
        suggestion: Any,
        message: IncomingMessage,
        send_mode: str,
        sent: bool,
    ) -> AutoReplyLog:
        log = AutoReplyLog(
            message_id=message.id,
            property_code=getattr(message, "property_code", None),
            ota=message.ota,
            intent=suggestion.intent.name,
            fine_intent=suggestion.fine_intent.name if suggestion.fine_intent else None,
            intent_confidence=suggestion.intent_confidence,
            generation_mode=suggestion.generation_mode,
            template_id=suggestion.template_id,
            reply_text=suggestion.reply_text,
            send_mode=send_mode,
            sent=sent,
            allow_auto_send=suggestion.allow_auto_send,
            sent_at=None,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------

    def get(self, log_id: int) -> Optional[AutoReplyLog]:
        return self.db.query(AutoReplyLog).get(log_id)

    def list_recent(
        self,
        *,
        limit: int = 50,
        property_code: Optional[str] = None,
        ota: Optional[str] = None,
    ) -> List[AutoReplyLog]:
        q = self.db.query(AutoReplyLog).filter(AutoReplyLog.is_active.is_(True))

        if property_code:
            q = q.filter(AutoReplyLog.property_code == property_code)

        if ota:
            q = q.filter(AutoReplyLog.ota == ota)

        q = q.order_by(AutoReplyLog.created_at.desc())
        if limit:
            q = q.limit(limit)
        return q.all()

    def list_for_message(self, message_id: int) -> List[AutoReplyLog]:
        return (
            self.db.query(AutoReplyLog)
            .filter(
                AutoReplyLog.is_active.is_(True),
                AutoReplyLog.message_id == message_id,
            )
            .order_by(AutoReplyLog.created_at.asc())
            .all()
        )

    def get_latest_for_message(self, message_id: int) -> Optional[AutoReplyLog]:
        """
        메시지별 최신 자동응답(log) 조회
        """
        stmt = (
            select(AutoReplyLog)
            .where(AutoReplyLog.message_id == message_id)
            .order_by(desc(AutoReplyLog.id))
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    # Human-in-the-loop 보정
    def mark_sent(
        self,
        log_id: int,
        *,
        edited_text: Optional[str] = None,
        edited_by: Optional[str] = None,
    ) -> Optional[AutoReplyLog]:
        log = self.db.query(AutoReplyLog).get(log_id)
        if not log:
            return None

        if edited_text and edited_text.strip():
            log.edited = True
            log.edited_text = edited_text.strip()
            log.edited_by = edited_by

        from sqlalchemy.sql import func as _func
        log.sent = True
        log.sent_at = _func.now()

        self.db.commit()
        self.db.refresh(log)
        return log

    def mark_failed(self, log_id: int, reason: str) -> Optional[AutoReplyLog]:
        log = self.db.query(AutoReplyLog).get(log_id)
        if not log:
            return None
        log.failure_reason = reason
        log.sent = False
        self.db.commit()
        self.db.refresh(log)
        return log
