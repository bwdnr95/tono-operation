# backend/app/api/v1/__init__.py

from fastapi import APIRouter

from app.api.v1 import messages, auto_reply

api_router = APIRouter()

# 메시지 CRUD 등
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])

# 자동응답: 이미 /messages prefix를 들고 있으니까 prefix 없이 include
api_router.include_router(auto_reply.router)
