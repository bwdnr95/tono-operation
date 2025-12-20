"""
Commitment API 엔드포인트

- GET /conversations/{airbnb_thread_id}/commitments - 활성 Commitment 목록
- GET /conversations/{airbnb_thread_id}/risk-signals - 미해결 Risk Signal 목록
- POST /conversations/{airbnb_thread_id}/risk-signals/{signal_id}/resolve - Risk Signal 해결
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.models.conversation import Conversation, ConversationChannel
from app.domain.models.commitment import Commitment, RiskSignal, CommitmentStatus
from app.repositories.commitment_repository import CommitmentRepository, RiskSignalRepository
from app.services.send_event_handler import SendEventHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["commitments"])


# ─────────────────────────────────────────────────────────────
# DTOs
# ─────────────────────────────────────────────────────────────

class CommitmentDTO(BaseModel):
    id: str
    topic: str
    type: str
    value: dict
    provenance_text: str
    status: str
    extraction_confidence: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class CommitmentListResponse(BaseModel):
    airbnb_thread_id: str
    commitments: List[CommitmentDTO]
    total: int


class RiskSignalDTO(BaseModel):
    id: str
    signal_type: str
    severity: str
    message: str
    resolved: bool
    created_at: datetime
    related_commitment_id: Optional[str] = None
    details: dict
    
    class Config:
        from_attributes = True


class RiskSignalListResponse(BaseModel):
    airbnb_thread_id: str
    signals: List[RiskSignalDTO]
    total: int


class ConflictCheckRequest(BaseModel):
    draft_text: str


class ConflictDTO(BaseModel):
    has_conflict: bool
    type: Optional[str]
    severity: Optional[str]
    message: str
    existing_commitment: Optional[CommitmentDTO]


class ConflictCheckResponse(BaseModel):
    airbnb_thread_id: str
    conflicts: List[ConflictDTO]
    has_any_conflict: bool


# ─────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────

def _get_conversation_by_thread(db: Session, airbnb_thread_id: str) -> Optional[Conversation]:
    """airbnb_thread_id로 Conversation 조회"""
    return db.execute(
        select(Conversation)
        .where(Conversation.airbnb_thread_id == airbnb_thread_id)
        .limit(1)
    ).scalar_one_or_none()


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/{airbnb_thread_id}/commitments", response_model=CommitmentListResponse)
def get_commitments(
    airbnb_thread_id: str,
    status: Optional[str] = Query(None, description="Filter by status: active, superseded, expired"),
    db: Session = Depends(get_db),
):
    """
    대화의 Commitment 목록 조회
    
    - 기본: ACTIVE 상태만 반환
    - status 파라미터로 필터링 가능
    """
    repo = CommitmentRepository(db)
    
    if status:
        # 특정 상태로 필터링
        stmt = (
            select(Commitment)
            .where(Commitment.airbnb_thread_id == airbnb_thread_id)
            .where(Commitment.status == status)
            .order_by(Commitment.created_at.desc())
        )
        commitments = list(db.execute(stmt).scalars().all())
    else:
        # 기본: ACTIVE만
        commitments = repo.get_active_by_thread_id(airbnb_thread_id)
    
    return CommitmentListResponse(
        airbnb_thread_id=airbnb_thread_id,
        commitments=[
            CommitmentDTO(
                id=str(c.id),
                topic=c.topic,
                type=c.type,
                value=c.value,
                provenance_text=c.provenance_text,
                status=c.status,
                extraction_confidence=c.extraction_confidence,
                created_at=c.created_at,
            )
            for c in commitments
        ],
        total=len(commitments),
    )


@router.get("/{airbnb_thread_id}/risk-signals", response_model=RiskSignalListResponse)
def get_risk_signals(
    airbnb_thread_id: str,
    include_resolved: bool = Query(False, description="Include resolved signals"),
    db: Session = Depends(get_db),
):
    """
    대화의 Risk Signal 목록 조회
    
    - 기본: 미해결 Signal만 반환
    - include_resolved=true로 전체 조회 가능
    """
    conv = _get_conversation_by_thread(db, airbnb_thread_id)
    if not conv:
        return RiskSignalListResponse(
            airbnb_thread_id=airbnb_thread_id,
            signals=[],
            total=0,
        )
    
    repo = RiskSignalRepository(db)
    
    if include_resolved:
        # 전체 조회
        stmt = (
            select(RiskSignal)
            .where(RiskSignal.conversation_id == conv.id)
            .order_by(RiskSignal.created_at.desc())
        )
        signals = list(db.execute(stmt).scalars().all())
    else:
        # 미해결만
        signals = repo.get_unresolved_by_conversation(conv.id)
    
    return RiskSignalListResponse(
        airbnb_thread_id=airbnb_thread_id,
        signals=[
            RiskSignalDTO(
                id=str(s.id),
                signal_type=s.signal_type,
                severity=s.severity,
                message=s.message,
                resolved=s.resolved,
                created_at=s.created_at,
                related_commitment_id=str(s.related_commitment_id) if s.related_commitment_id else None,
                details=s.details,
            )
            for s in signals
        ],
        total=len(signals),
    )


@router.post("/{airbnb_thread_id}/risk-signals/{signal_id}/resolve")
def resolve_risk_signal(
    airbnb_thread_id: str,
    signal_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Risk Signal 해결 처리
    
    호스트가 경고를 확인하고 "확인함" 버튼 누를 때 호출
    """
    conv = _get_conversation_by_thread(db, airbnb_thread_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Signal 조회
    signal = db.execute(
        select(RiskSignal)
        .where(RiskSignal.id == signal_id)
        .where(RiskSignal.conversation_id == conv.id)
    ).scalar_one_or_none()
    
    if not signal:
        raise HTTPException(status_code=404, detail="Risk signal not found")
    
    if signal.resolved:
        return {"status": "already_resolved", "signal_id": str(signal_id)}
    
    # 해결 처리
    repo = RiskSignalRepository(db)
    repo.resolve(signal_id, resolved_by="host")
    db.commit()
    
    return {"status": "resolved", "signal_id": str(signal_id)}


@router.post("/{airbnb_thread_id}/check-conflicts", response_model=ConflictCheckResponse)
async def check_draft_conflicts(
    airbnb_thread_id: str,
    body: ConflictCheckRequest,
    db: Session = Depends(get_db),
):
    """
    Draft가 기존 Commitment와 충돌하는지 검사
    
    발송 전에 호출하여 호스트에게 경고 표시
    """
    handler = SendEventHandler(db)
    conflicts = await handler.check_draft_conflicts(
        draft_text=body.draft_text,
        airbnb_thread_id=airbnb_thread_id,
    )
    
    return ConflictCheckResponse(
        airbnb_thread_id=airbnb_thread_id,
        conflicts=[
            ConflictDTO(
                has_conflict=c["has_conflict"],
                type=c.get("type"),
                severity=c.get("severity"),
                message=c.get("message", ""),
                existing_commitment=CommitmentDTO(
                    id=c["existing_commitment"]["id"],
                    topic=c["existing_commitment"]["topic"],
                    type=c["existing_commitment"]["type"],
                    value=c["existing_commitment"]["value"],
                    provenance_text=c["existing_commitment"]["provenance_text"],
                    status=c["existing_commitment"]["status"],
                    extraction_confidence=0.0,
                    created_at=datetime.fromisoformat(c["existing_commitment"]["created_at"]),
                ) if c.get("existing_commitment") else None,
            )
            for c in conflicts
        ],
        has_any_conflict=any(c["has_conflict"] for c in conflicts),
    )


@router.get("/{airbnb_thread_id}/commitment-context")
def get_commitment_context(
    airbnb_thread_id: str,
    db: Session = Depends(get_db),
):
    """
    LLM Context용 Commitment 문자열 반환
    
    디버깅/테스트용 엔드포인트
    """
    handler = SendEventHandler(db)
    context = handler.get_active_commitments_for_draft(airbnb_thread_id)
    
    return {
        "airbnb_thread_id": airbnb_thread_id,
        "commitment_context": context,
    }
