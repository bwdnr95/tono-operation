# backend/app/api/v1/api.py

from fastapi import APIRouter

from app.api.v1 import (
    messages,
    message_intent_labels,
    auto_reply,
    auto_replies,
    staff_notifications,
    gmail_jobs,
    conversations,
    bulk_send,
)

api_router = APIRouter()

# 각 router가 자기 prefix를 들고 있으므로 여기서는 prefix를 주지 않는다.
api_router.include_router(messages.router)
api_router.include_router(message_intent_labels.router)
api_router.include_router(auto_reply.router)

# ✅ 최근 AutoReply 로그 조회용
api_router.include_router(auto_replies.router)

# ✅ 스태프 알림용
api_router.include_router(staff_notifications.router)

# ✅ Gmail Airbnb 자동응답 잡용
api_router.include_router(gmail_jobs.router)

# ✅ Conversation (thread 기반)
api_router.include_router(conversations.router)

# ✅ Bulk Send (thread 기반)
api_router.include_router(bulk_send.router)
