# backend/app/api/v1/auto_replies.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.auto_reply_log_repository import AutoReplyLogRepository
from app.repositories.messages import IncomingMessageRepository
from app.domain.models.auto_reply_log import AutoReplyLog
from app.domain.intents import MessageActor, MessageActionability  # 🔹 추가


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class AutoReplyLogOut(BaseModel):
    id: int
    message_id: int
    property_code: Optional[str]
    ota: Optional[str]
    subject: Optional[str]
    pure_guest_message: Optional[str]

    intent: str
    fine_intent: Optional[str]
    intent_confidence: float

    reply_text: str
    generation_mode: str
    template_id: Optional[int]

    send_mode: str      # AUTOPILOT / HITL
    sent: bool
    created_at: datetime

    class Config:
        orm_mode = True


router = APIRouter(
    prefix="/auto-replies",
    tags=["auto_replies"],
)


def _fetch_recent_auto_replies(
    *,
    db: Session,
    property_code: Optional[str],
    ota: Optional[str],
    limit: int,
) -> List[AutoReplyLogOut]:
    """
    실제로 최근 AutoReply 로그를 조회해서 DTO 리스트로 변환하는 내부 함수.
    /auto-replies 와 /auto-replies/recent 두 곳에서 공통으로 사용.

    ✅ 여기서 "게스트 + 답장 필요" 메시지만 포함하도록 필터링한다.
    """
    log_repo = AutoReplyLogRepository(db)
    msg_repo = IncomingMessageRepository(db)

    logs: List[AutoReplyLog] = log_repo.list_recent(
        property_code=property_code,
        ota=ota,
        limit=limit,
    )

    results: List[AutoReplyLogOut] = []

    for log in logs:
        msg = msg_repo.get(log.message_id)

        # 메시지가 없으면 스킵
        if msg is None:
            continue

        # 🔹 시스템/호스트/답장 불필요 메시지는 자동응답 리스트에서 제외
        if msg.sender_actor != MessageActor.GUEST:
            continue
        if msg.actionability != MessageActionability.NEEDS_REPLY:
            continue

        results.append(
            AutoReplyLogOut(
                id=log.id,
                message_id=log.message_id,
                property_code=log.property_code,
                ota=log.ota,
                subject=msg.subject,
                pure_guest_message=msg.pure_guest_message,
                intent=log.intent,
                fine_intent=log.fine_intent,
                intent_confidence=log.intent_confidence or 0.0,
                reply_text=log.reply_text,
                generation_mode=log.generation_mode or "",
                template_id=log.template_id,
                send_mode=log.send_mode,
                sent=log.sent,
                created_at=log.created_at,
            )
        )

    return results


@router.get("", response_model=List[AutoReplyLogOut])
def list_auto_replies(
    property_code: Optional[str] = Query(None),
    ota: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    ✅ 프론트가 사용 중인 엔드포인트:
        GET /api/v1/auto-replies?limit=50

    최근 AutoReply 로그 리스트 조회.
    """
    return _fetch_recent_auto_replies(
        db=db,
        property_code=property_code,
        ota=ota,
        limit=limit,
    )


@router.get("/recent", response_model=List[AutoReplyLogOut])
def list_recent_auto_replies(
    property_code: Optional[str] = Query(None),
    ota: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    과거에 사용하던 엔드포인트.
    (기존 /recent 호출하는 곳이 있다면 그대로 유지)
    """
    return _fetch_recent_auto_replies(
        db=db,
        property_code=property_code,
        ota=ota,
        limit=limit,
    )
