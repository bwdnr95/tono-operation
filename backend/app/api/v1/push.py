# backend/app/api/v1/push.py
"""
Push Notification API

- GET /push/vapid-public-key: VAPID 공개키 조회
- POST /push/subscribe: Push 구독 등록
- POST /push/unsubscribe: Push 구독 해제
- POST /push/test: 테스트 Push 전송 (개발용)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.push_service import PushService

router = APIRouter(prefix="/push", tags=["push"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request/Response Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PushSubscriptionRequest(BaseModel):
    """Push 구독 요청"""
    endpoint: str
    keys: dict  # { p256dh: str, auth: str }


class PushUnsubscribeRequest(BaseModel):
    """Push 구독 해제 요청"""
    endpoint: str


class VapidKeyResponse(BaseModel):
    """VAPID 공개키 응답"""
    public_key: str


class PushTestRequest(BaseModel):
    """테스트 Push 요청"""
    title: str = "🔔 테스트 알림"
    body: str = "Push 알림이 정상적으로 작동합니다!"
    url: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/vapid-public-key", response_model=VapidKeyResponse)
def get_vapid_public_key(db: Session = Depends(get_db)):
    """
    VAPID 공개키 조회
    
    프론트엔드에서 Push 구독 시 필요한 applicationServerKey
    """
    service = PushService(db)
    public_key = service.get_vapid_public_key()
    
    if not public_key:
        raise HTTPException(
            status_code=503,
            detail="Push notifications not configured (VAPID_PUBLIC_KEY missing)"
        )
    
    return VapidKeyResponse(public_key=public_key)


@router.post("/subscribe")
def subscribe(
    request: PushSubscriptionRequest,
    db: Session = Depends(get_db),
):
    """
    Push 구독 등록
    
    브라우저에서 PushSubscription 객체를 받아서 저장
    """
    service = PushService(db)
    
    p256dh = request.keys.get("p256dh")
    auth = request.keys.get("auth")
    
    if not p256dh or not auth:
        raise HTTPException(
            status_code=400,
            detail="Missing required keys: p256dh, auth"
        )
    
    success = service.subscribe(
        endpoint=request.endpoint,
        p256dh_key=p256dh,
        auth_key=auth,
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save subscription")
    
    return {"status": "subscribed"}


@router.post("/unsubscribe")
def unsubscribe(
    request: PushUnsubscribeRequest,
    db: Session = Depends(get_db),
):
    """
    Push 구독 해제
    """
    service = PushService(db)
    service.unsubscribe(request.endpoint)
    return {"status": "unsubscribed"}


@router.post("/test")
def send_test_push(
    request: PushTestRequest,
    db: Session = Depends(get_db),
):
    """
    테스트 Push 전송 (개발용)
    
    모든 활성 구독자에게 테스트 알림 전송
    """
    service = PushService(db)
    result = service.send_to_all(
        title=request.title,
        body=request.body,
        url=request.url,
    )
    
    return {
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "failed_endpoints": result.failed_endpoints[:5],  # 최대 5개만
    }
