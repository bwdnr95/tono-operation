from fastapi import APIRouter

from app.api.v1 import messages, message_intent_labels, auto_reply

api_router = APIRouter()

# 각 router가 자기 prefix를 들고 있으므로 여기서는 prefix를 주지 않는다.
api_router.include_router(messages.router)                
api_router.include_router(message_intent_labels.router)   
api_router.include_router(auto_reply.router)              
