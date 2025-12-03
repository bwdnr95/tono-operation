from fastapi import APIRouter

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.get("/health")
def webhook_health():
    return {"status": "ok"}