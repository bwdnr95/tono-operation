# backend/app/api/v1/api.py
"""
TONO API Router
- Conversation 기반 API만 유지
- Message 기반 API 제거됨
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.v1 import (
    staff_notifications,
    conversations,
    bulk_send,
    commitments,
    test_oc,  # 테스트용
    properties,  # 숙소 관리
    dashboard,  # 대시보드
)

api_router = APIRouter()

# ✅ Conversation (thread 기반) - 핵심 API
api_router.include_router(conversations.router)

# ✅ Bulk Send (thread 기반)
api_router.include_router(bulk_send.router)

# ✅ Staff Notification & OC (OC 기반)
api_router.include_router(staff_notifications.router)

# ✅ Commitment Memory (약속 기억)
api_router.include_router(commitments.router)

# ✅ Property Management (숙소 관리)
api_router.include_router(properties.router)

# ✅ Dashboard (대시보드)
api_router.include_router(dashboard.router)

# 🧪 Test API (Production에서 제거)
api_router.include_router(test_oc.router)


# ============================================================
# Scheduler API (테스트/관리용)
# ============================================================

class SchedulerStatusResponse(BaseModel):
    running: bool
    interval_minutes: int | None
    next_run: str | None


@api_router.get("/scheduler/status", response_model=SchedulerStatusResponse, tags=["Scheduler"])
def get_scheduler_status():
    """스케줄러 상태 조회"""
    from app.services.scheduler import get_scheduler
    
    scheduler = get_scheduler()
    if scheduler is None:
        return SchedulerStatusResponse(running=False, interval_minutes=None, next_run=None)
    
    job = scheduler.get_job("gmail_ingest_job")
    next_run = None
    if job and job.next_run_time:
        next_run = job.next_run_time.isoformat()
    
    return SchedulerStatusResponse(
        running=scheduler.running,
        interval_minutes=5,
        next_run=next_run,
    )


@api_router.post("/scheduler/run-now", tags=["Scheduler"])
async def run_scheduler_now():
    """스케줄러 Job 즉시 실행 (테스트용)"""
    from app.services.scheduler import gmail_ingest_job
    
    try:
        await gmail_ingest_job()
        return {"status": "ok", "message": "Job 실행 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
