"""
TONO Orchestrator API Endpoints

Decision 로그 조회, 통계, 패턴 관리 등
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.models.orchestrator import (
    DecisionLog,
    AutomationPattern,
    PolicyRule,
)
from app.services.orchestrator_core import OrchestratorCore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


# ═══════════════════════════════════════════════════════════════════
# DTOs
# ═══════════════════════════════════════════════════════════════════

class DecisionLogDTO(BaseModel):
    id: UUID
    conversation_id: UUID
    airbnb_thread_id: str
    property_code: Optional[str]
    decision: str
    reason_codes: List[str]
    confidence: float
    human_action: Optional[str]
    was_sent: bool
    created_at: datetime


class DecisionStatsDTO(BaseModel):
    total: int
    by_decision: dict
    by_human_action: dict
    automation_candidates: int
    automation_rate: float
    period_days: int


class SummaryStatsDTO(BaseModel):
    """대시보드용 요약 통계"""
    period_days: int
    total_decisions: int
    sent_count: int
    blocked_count: int
    # 자동화 지표
    approved_as_is: int
    approved_with_edit: int
    automation_rate: float
    # 트렌드
    automation_trend: str  # "improving", "stable", "declining"


# ═══════════════════════════════════════════════════════════════════
# Decision Logs API
# ═══════════════════════════════════════════════════════════════════

@router.get("/decisions", response_model=List[DecisionLogDTO])
def list_decisions(
    property_code: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    human_action: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Decision 로그 목록 조회"""
    since = datetime.utcnow() - timedelta(days=days)
    
    stmt = select(DecisionLog).where(
        DecisionLog.created_at >= since
    ).order_by(desc(DecisionLog.created_at)).limit(limit)
    
    if property_code:
        stmt = stmt.where(DecisionLog.property_code == property_code)
    if decision:
        stmt = stmt.where(DecisionLog.decision == decision)
    if human_action:
        stmt = stmt.where(DecisionLog.human_action == human_action)
    
    logs = db.execute(stmt).scalars().all()
    
    return [
        DecisionLogDTO(
            id=log.id,
            conversation_id=log.conversation_id,
            airbnb_thread_id=log.airbnb_thread_id,
            property_code=log.property_code,
            decision=log.decision,
            reason_codes=log.reason_codes or [],
            confidence=log.confidence,
            human_action=log.human_action,
            was_sent=log.was_sent,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get("/decisions/{decision_log_id}")
def get_decision_detail(
    decision_log_id: UUID,
    db: Session = Depends(get_db),
):
    """Decision 로그 상세 조회"""
    log = db.get(DecisionLog, decision_log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Decision log not found")
    
    return {
        "id": str(log.id),
        "conversation_id": str(log.conversation_id),
        "draft_id": str(log.draft_id) if log.draft_id else None,
        "airbnb_thread_id": log.airbnb_thread_id,
        "property_code": log.property_code,
        "guest_message": log.guest_message,
        "draft_content": log.draft_content,
        "context_snapshot": log.context_snapshot,
        "decision": log.decision,
        "reason_codes": log.reason_codes,
        "decision_details": log.decision_details,
        "confidence": log.confidence,
        "human_action": log.human_action,
        "human_action_at": log.human_action_at.isoformat() if log.human_action_at else None,
        "edited_content": log.edited_content,
        "was_sent": log.was_sent,
        "sent_at": log.sent_at.isoformat() if log.sent_at else None,
        "final_content": log.final_content,
        "created_at": log.created_at.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# Statistics API
# ═══════════════════════════════════════════════════════════════════

@router.get("/stats", response_model=DecisionStatsDTO)
def get_decision_stats(
    property_code: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Decision 통계 조회"""
    orchestrator = OrchestratorCore(db)
    stats = orchestrator.get_decision_stats(property_code=property_code, days=days)
    
    total_with_action = sum(stats["by_human_action"].values())
    automation_rate = 0.0
    if total_with_action > 0:
        automation_rate = stats["automation_candidates"] / total_with_action
    
    return DecisionStatsDTO(
        total=stats["total"],
        by_decision=stats["by_decision"],
        by_human_action=stats["by_human_action"],
        automation_candidates=stats["automation_candidates"],
        automation_rate=automation_rate,
        period_days=days,
    )


@router.get("/stats/summary", response_model=SummaryStatsDTO)
def get_summary_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """대시보드용 요약 통계"""
    from sqlalchemy import Integer, case
    
    since = datetime.utcnow() - timedelta(days=days)
    
    # 전체 통계
    stmt = select(
        func.count().label("total"),
        func.sum(func.cast(DecisionLog.was_sent, Integer)).label("sent"),
    ).where(DecisionLog.created_at >= since)
    
    result = db.execute(stmt).one()
    total = result.total or 0
    sent = result.sent or 0
    
    # Human action별 통계
    action_stmt = select(
        DecisionLog.human_action,
        func.count().label("count"),
    ).where(
        DecisionLog.created_at >= since,
        DecisionLog.human_action.isnot(None),
    ).group_by(DecisionLog.human_action)
    
    action_results = db.execute(action_stmt).all()
    
    approved_as_is = 0
    approved_with_edit = 0
    for row in action_results:
        if row.human_action == "approved_as_is":
            approved_as_is = row.count
        elif row.human_action == "approved_with_edit":
            approved_with_edit = row.count
    
    total_approved = approved_as_is + approved_with_edit
    automation_rate = approved_as_is / total_approved if total_approved > 0 else 0.0
    
    # 트렌드 계산 (이전 기간 대비)
    prev_since = since - timedelta(days=days)
    prev_stmt = select(
        DecisionLog.human_action,
        func.count().label("count"),
    ).where(
        DecisionLog.created_at >= prev_since,
        DecisionLog.created_at < since,
        DecisionLog.human_action.isnot(None),
    ).group_by(DecisionLog.human_action)
    
    prev_results = db.execute(prev_stmt).all()
    prev_as_is = 0
    prev_total = 0
    for row in prev_results:
        prev_total += row.count
        if row.human_action == "approved_as_is":
            prev_as_is = row.count
    
    prev_rate = prev_as_is / prev_total if prev_total > 0 else 0.0
    
    if automation_rate > prev_rate + 0.05:
        trend = "improving"
    elif automation_rate < prev_rate - 0.05:
        trend = "declining"
    else:
        trend = "stable"
    
    return SummaryStatsDTO(
        period_days=days,
        total_decisions=total,
        sent_count=sent,
        blocked_count=total - sent,
        approved_as_is=approved_as_is,
        approved_with_edit=approved_with_edit,
        automation_rate=automation_rate,
        automation_trend=trend,
    )


# ═══════════════════════════════════════════════════════════════════
# Automation Patterns API
# ═══════════════════════════════════════════════════════════════════

@router.get("/patterns")
def list_patterns(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """자동화 패턴 목록 조회"""
    stmt = select(AutomationPattern).order_by(desc(AutomationPattern.created_at))
    
    if is_active is not None:
        stmt = stmt.where(AutomationPattern.is_active == is_active)
    
    patterns = db.execute(stmt).scalars().all()
    
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "conditions": p.conditions,
            "property_code": p.property_code,
            "total_matches": p.total_matches,
            "approval_rate": p.approval_rate,
            "is_auto_approved": p.is_auto_approved,
            "is_eligible": p.is_eligible_for_automation,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat(),
        }
        for p in patterns
    ]


class ApprovePatternRequest(BaseModel):
    approve: bool


@router.post("/patterns/{pattern_id}/approve")
def approve_pattern(
    pattern_id: UUID,
    body: ApprovePatternRequest,
    db: Session = Depends(get_db),
):
    """패턴 자동화 승인/거부"""
    pattern = db.get(AutomationPattern, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    
    if body.approve:
        if not pattern.is_eligible_for_automation:
            raise HTTPException(
                status_code=400, 
                detail=f"Pattern not eligible. Need {pattern.min_sample_size} samples with {pattern.min_approval_rate*100}% approval rate."
            )
        pattern.is_auto_approved = True
        pattern.auto_approved_at = datetime.utcnow()
        pattern.auto_approved_by = "admin"  # TODO: 실제 사용자
    else:
        pattern.is_auto_approved = False
        pattern.auto_approved_at = None
        pattern.auto_approved_by = None
    
    db.commit()
    
    return {"success": True, "is_auto_approved": pattern.is_auto_approved}


# ═══════════════════════════════════════════════════════════════════
# Policy Rules API
# ═══════════════════════════════════════════════════════════════════

@router.get("/policies")
def list_policies(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """정책 규칙 목록 조회"""
    stmt = select(PolicyRule).order_by(PolicyRule.priority)
    
    if is_active is not None:
        stmt = stmt.where(PolicyRule.is_active == is_active)
    
    rules = db.execute(stmt).scalars().all()
    
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "rule_type": r.rule_type,
            "conditions": r.conditions,
            "resulting_decision": r.resulting_decision,
            "priority": r.priority,
            "is_active": r.is_active,
            "source": r.source,
            "created_at": r.created_at.isoformat(),
        }
        for r in rules
    ]


class CreatePolicyRequest(BaseModel):
    name: str
    description: str
    rule_type: str  # "block", "review", "allow"
    conditions: dict
    resulting_decision: str
    priority: int = 100
    property_code: Optional[str] = None


@router.post("/policies")
def create_policy(
    body: CreatePolicyRequest,
    db: Session = Depends(get_db),
):
    """정책 규칙 생성"""
    rule = PolicyRule(
        name=body.name,
        description=body.description,
        rule_type=body.rule_type,
        conditions=body.conditions,
        resulting_decision=body.resulting_decision,
        priority=body.priority,
        property_code=body.property_code,
        source="manual",
        created_by="admin",  # TODO: 실제 사용자
    )
    
    db.add(rule)
    db.commit()
    
    return {"id": str(rule.id), "name": rule.name}


@router.delete("/policies/{policy_id}")
def delete_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
):
    """정책 규칙 삭제 (비활성화)"""
    rule = db.get(PolicyRule, policy_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    rule.is_active = False
    db.commit()
    
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# Property FAQ Auto Send Stats API
# ═══════════════════════════════════════════════════════════════════

class PropertyFaqStatsDTO(BaseModel):
    id: str
    property_code: str
    faq_key: str
    total_count: int
    approved_count: int
    approved_with_edit_count: int
    rejected_count: int
    approval_rate: float
    eligible_for_auto_send: bool
    last_approved_at: Optional[str]
    last_rejected_at: Optional[str]


class PropertyFaqStatsSummaryDTO(BaseModel):
    total_eligible_count: int
    properties_with_auto_send: int
    by_property: dict


@router.get("/auto-send-stats", response_model=List[PropertyFaqStatsDTO])
def get_auto_send_stats(
    property_code: Optional[str] = Query(None),
    eligible_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Property + FAQ별 AUTO_SEND 통계 조회"""
    from app.services.property_faq_auto_send_service import PropertyFaqAutoSendService
    
    service = PropertyFaqAutoSendService(db)
    
    if property_code:
        stats = service.get_stats_for_property(property_code)
    elif eligible_only:
        stats = service.get_all_eligible_stats()
    else:
        # 전체 조회는 eligible만 반환 (너무 많을 수 있으므로)
        stats = service.get_all_eligible_stats()
    
    return stats


@router.get("/auto-send-stats/summary", response_model=PropertyFaqStatsSummaryDTO)
def get_auto_send_stats_summary(
    db: Session = Depends(get_db),
):
    """AUTO_SEND 통계 요약"""
    from app.services.property_faq_auto_send_service import PropertyFaqAutoSendService
    
    service = PropertyFaqAutoSendService(db)
    return service.get_stats_summary()


@router.get("/auto-send-stats/{property_code}/eligible-keys")
def get_eligible_faq_keys(
    property_code: str,
    db: Session = Depends(get_db),
):
    """특정 숙소의 AUTO_SEND 가능한 faq_key 목록"""
    from app.services.property_faq_auto_send_service import PropertyFaqAutoSendService
    
    service = PropertyFaqAutoSendService(db)
    keys = service.get_eligible_faq_keys(property_code)
    
    return {
        "property_code": property_code,
        "eligible_faq_keys": keys,
        "count": len(keys),
    }


@router.post("/auto-send-stats/check-eligible")
def check_auto_send_eligible(
    property_code: str = Query(...),
    faq_keys: str = Query(..., description="Comma-separated faq keys"),
    db: Session = Depends(get_db),
):
    """AUTO_SEND 가능 여부 확인"""
    from app.services.property_faq_auto_send_service import PropertyFaqAutoSendService
    
    service = PropertyFaqAutoSendService(db)
    keys = [k.strip() for k in faq_keys.split(",") if k.strip()]
    
    is_eligible = service.is_eligible_for_auto_send(property_code, keys)
    
    return {
        "property_code": property_code,
        "faq_keys": keys,
        "is_eligible": is_eligible,
    }
