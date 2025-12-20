"""
OC 테스트 API

수동 테스트용 - Production에서는 제거할 것

POST /test/ocs - OC 직접 생성
POST /test/ocs/sample-set - 샘플 OC 세트 생성 (priority별)
DELETE /test/ocs - 모든 OC 삭제
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.models.conversation import Conversation
from app.domain.models.operational_commitment import (
    OperationalCommitment,
    OCStatus,
    OCTargetTimeType,
    OCTopic,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/test", tags=["test"])


# ============================================================
# DTOs
# ============================================================

class CreateOCRequest(BaseModel):
    conversation_id: Optional[str] = None  # 없으면 첫 번째 conversation 사용
    airbnb_thread_id: Optional[str] = None
    topic: str  # early_checkin, follow_up, facility_issue, refund_check, payment, compensation
    description: str
    evidence_quote: str
    target_time_type: str = "implicit"  # explicit, implicit
    target_date: Optional[str] = None  # YYYY-MM-DD
    is_candidate_only: bool = False


class CreateOCResponse(BaseModel):
    oc_id: str
    topic: str
    description: str
    priority: str
    status: str


class SampleSetResponse(BaseModel):
    created: List[CreateOCResponse]
    message: str


# ============================================================
# Endpoints
# ============================================================

@router.post("/ocs", response_model=CreateOCResponse)
def create_test_oc(
    req: CreateOCRequest,
    db: Session = Depends(get_db),
):
    """
    테스트용 OC 직접 생성
    """
    # Conversation 찾기
    if req.conversation_id:
        conv = db.execute(
            select(Conversation).where(Conversation.id == req.conversation_id)
        ).scalar_one_or_none()
    elif req.airbnb_thread_id:
        conv = db.execute(
            select(Conversation).where(Conversation.airbnb_thread_id == req.airbnb_thread_id)
        ).scalar_one_or_none()
    else:
        # 첫 번째 conversation 사용
        conv = db.execute(
            select(Conversation).order_by(Conversation.created_at.desc()).limit(1)
        ).scalar_one_or_none()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found. Create one first.")
    
    # target_date 파싱
    target_date = None
    if req.target_date:
        target_date = date.fromisoformat(req.target_date)
    
    # OC 생성
    oc = OperationalCommitment(
        id=uuid4(),
        conversation_id=conv.id,
        topic=req.topic,
        description=req.description,
        evidence_quote=req.evidence_quote,
        target_time_type=req.target_time_type,
        target_date=target_date,
        status=OCStatus.pending.value,
        is_candidate_only=req.is_candidate_only,
        extraction_confidence=0.9,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    db.add(oc)
    db.commit()
    
    # Priority 계산
    priority = oc.calculate_priority(date.today())
    
    return CreateOCResponse(
        oc_id=str(oc.id),
        topic=oc.topic,
        description=oc.description,
        priority=priority.value,
        status=oc.status,
    )


@router.post("/ocs/sample-set", response_model=SampleSetResponse)
def create_sample_oc_set(
    db: Session = Depends(get_db),
):
    """
    샘플 OC 세트 생성 (priority별 테스트용)
    
    생성되는 OC:
    1. 🔴 Immediate - 얼리체크인 (오늘)
    2. 🔴 Immediate - 시설문제 (implicit)
    3. 🟡 Upcoming - 얼리체크인 (내일)
    4. ⚪ Pending - 후속안내 (모레)
    5. 🟣 Candidate - 환불 확인 (운영자 확정 필요)
    6. 🟢 Suggested Resolve - 시설문제 해소 제안
    """
    # 첫 번째 conversation 찾기
    conv = db.execute(
        select(Conversation).order_by(Conversation.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    
    if not conv:
        raise HTTPException(
            status_code=404, 
            detail="Conversation not found. Run Gmail Ingest first to create conversations."
        )
    
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    
    samples = [
        # 1. 🔴 Immediate - 오늘 체크인 얼리체크인
        {
            "topic": OCTopic.early_checkin.value,
            "description": "14시 얼리체크인 허용",
            "evidence_quote": "네, 14시에 입실 가능합니다. 도착하시면 연락주세요.",
            "target_time_type": OCTargetTimeType.explicit.value,
            "target_date": today,
            "status": OCStatus.pending.value,
            "is_candidate_only": False,
        },
        # 2. 🔴 Immediate - 시설문제 (implicit = 즉시)
        {
            "topic": OCTopic.facility_issue.value,
            "description": "에어컨 수리 예정",
            "evidence_quote": "에어컨 점검 후 수리 조치하겠습니다.",
            "target_time_type": OCTargetTimeType.implicit.value,
            "target_date": None,
            "status": OCStatus.pending.value,
            "is_candidate_only": False,
        },
        # 3. 🟡 Upcoming - 내일 체크인 얼리체크인
        {
            "topic": OCTopic.early_checkin.value,
            "description": "13시 얼리체크인 허용 (내일)",
            "evidence_quote": "내일 13시 입실 가능합니다.",
            "target_time_type": OCTargetTimeType.explicit.value,
            "target_date": tomorrow,
            "status": OCStatus.pending.value,
            "is_candidate_only": False,
        },
        # 4. ⚪ Pending - 모레 후속안내
        {
            "topic": OCTopic.follow_up.value,
            "description": "주변 맛집 안내 예정",
            "evidence_quote": "체크인 전날 주변 맛집 리스트 보내드리겠습니다.",
            "target_time_type": OCTargetTimeType.explicit.value,
            "target_date": day_after,
            "status": OCStatus.pending.value,
            "is_candidate_only": False,
        },
        # 5. 🟣 Candidate - 환불 (운영자 확정 필요)
        {
            "topic": OCTopic.refund_check.value,
            "description": "환불 처리 예정",
            "evidence_quote": "환불 진행해 드리겠습니다. 2-3일 내 처리됩니다.",
            "target_time_type": OCTargetTimeType.implicit.value,
            "target_date": None,
            "status": OCStatus.pending.value,
            "is_candidate_only": True,
        },
        # 6. 🟢 Suggested Resolve - 시설문제 해소 제안
        {
            "topic": OCTopic.facility_issue.value,
            "description": "온수 문제 조치 완료 (해소 제안됨)",
            "evidence_quote": "온수 보일러 점검하겠습니다.",
            "target_time_type": OCTargetTimeType.implicit.value,
            "target_date": None,
            "status": OCStatus.suggested_resolve.value,
            "is_candidate_only": False,
            "resolution_reason": "guest_cancelled",
            "resolution_evidence": "괜찮아요, 해결됐어요. 감사합니다!",  # 게스트 메시지
        },
    ]
    
    created = []
    
    for sample in samples:
        oc = OperationalCommitment(
            id=uuid4(),
            conversation_id=conv.id,
            topic=sample["topic"],
            description=sample["description"],
            evidence_quote=sample["evidence_quote"],
            target_time_type=sample["target_time_type"],
            target_date=sample.get("target_date"),
            status=sample["status"],
            resolution_reason=sample.get("resolution_reason"),
            resolution_evidence=sample.get("resolution_evidence"),
            is_candidate_only=sample["is_candidate_only"],
            extraction_confidence=0.9,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(oc)
        
        priority = oc.calculate_priority(today)
        created.append(CreateOCResponse(
            oc_id=str(oc.id),
            topic=oc.topic,
            description=oc.description,
            priority=priority.value,
            status=oc.status,
        ))
    
    db.commit()
    
    return SampleSetResponse(
        created=created,
        message=f"Created {len(created)} sample OCs for conversation {conv.airbnb_thread_id[:20]}..."
    )


@router.delete("/ocs")
def delete_all_test_ocs(
    db: Session = Depends(get_db),
):
    """
    모든 OC 삭제 (테스트 초기화용)
    """
    result = db.execute(delete(OperationalCommitment))
    db.commit()
    
    return {"deleted": result.rowcount, "message": "All OCs deleted"}
