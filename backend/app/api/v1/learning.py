# backend/app/api/v1/learning.py
"""
Learning Agent API

호스트 수정 데이터 분석 및 스타일 프로필 관련 엔드포인트
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.learning_agent import LearningAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/learning", tags=["learning"])


# ═══════════════════════════════════════════════════════════════
# Response Models
# ═══════════════════════════════════════════════════════════════

class EditPairDTO(BaseModel):
    draft_id: str
    conversation_id: str
    property_code: Optional[str]
    original: str
    edited: str
    guest_message: Optional[str]
    created_at: str
    was_sent: bool


class PatternDTO(BaseModel):
    pattern_type: str
    description: str
    frequency: int
    confidence: float
    examples: list


class StyleProfileDTO(BaseModel):
    profile_id: str
    profile_type: str
    tone: str
    sentence_endings: list
    greeting_style: str
    emoji_usage: str
    common_additions: list
    common_removals: list
    sample_count: int
    generated_at: str
    few_shot_examples: list
    prompt_context: str  # Draft Agent용 컨텍스트


class AnalysisReportDTO(BaseModel):
    summary: dict
    patterns: list
    profiles_by_property: dict
    recommendations: list


class EditStatsDTO(BaseModel):
    total_drafts: int
    edited_drafts: int
    edit_rate: float
    sent_drafts: int
    unedited_sent: int
    ai_adoption_rate: float
    by_property: dict


# ═══════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════

@router.get("/stats", response_model=EditStatsDTO)
def get_edit_stats(
    property_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    수정 통계 조회
    
    - 전체 draft 수
    - 수정된 draft 수
    - 수정률
    - AI 채택률 (무수정 발송 비율)
    """
    from sqlalchemy import select, func, and_
    from app.domain.models.conversation import DraftReply, Conversation, SendActionLog, SendAction
    
    # 기본 쿼리
    base_query = select(DraftReply).join(
        Conversation, DraftReply.conversation_id == Conversation.id
    )
    
    if property_code:
        base_query = base_query.where(Conversation.property_code == property_code)
    
    # 전체 draft 수
    total_drafts = db.execute(
        select(func.count()).select_from(base_query.subquery())
    ).scalar() or 0
    
    # 수정된 draft 수
    edited_query = base_query.where(DraftReply.is_edited == True)
    edited_drafts = db.execute(
        select(func.count()).select_from(edited_query.subquery())
    ).scalar() or 0
    
    # 발송된 conversation ID들
    sent_query = select(SendActionLog.conversation_id).where(
        SendActionLog.action == SendAction.send
    )
    if property_code:
        sent_query = sent_query.where(SendActionLog.property_code == property_code)
    
    sent_conv_ids = db.execute(sent_query).scalars().all()
    
    # 발송된 draft 수
    sent_drafts = len(sent_conv_ids)
    
    # 무수정 발송 수
    unedited_sent = 0
    if sent_conv_ids:
        unedited_sent = db.execute(
            select(func.count(DraftReply.id)).where(
                and_(
                    DraftReply.conversation_id.in_(sent_conv_ids),
                    DraftReply.is_edited == False
                )
            )
        ).scalar() or 0
    
    # 숙소별 통계
    by_property = {}
    if not property_code:
        prop_stats = db.execute(
            select(
                Conversation.property_code,
                func.count(DraftReply.id).label("total"),
                func.sum(func.cast(DraftReply.is_edited, Integer)).label("edited")
            )
            .join(Conversation, DraftReply.conversation_id == Conversation.id)
            .where(Conversation.property_code.isnot(None))
            .group_by(Conversation.property_code)
        ).all()
        
        for prop, total, edited in prop_stats:
            if prop and total > 0:
                by_property[prop] = {
                    "total": total,
                    "edited": edited or 0,
                    "edit_rate": round((edited or 0) / total * 100, 1)
                }
    
    edit_rate = round(edited_drafts / total_drafts * 100, 1) if total_drafts > 0 else 0
    ai_adoption_rate = round(unedited_sent / sent_drafts * 100, 1) if sent_drafts > 0 else 0
    
    return EditStatsDTO(
        total_drafts=total_drafts,
        edited_drafts=edited_drafts,
        edit_rate=edit_rate,
        sent_drafts=sent_drafts,
        unedited_sent=unedited_sent,
        ai_adoption_rate=ai_adoption_rate,
        by_property=by_property,
    )


@router.get("/edit-pairs")
def get_edit_pairs(
    property_code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    수정된 원본-수정 쌍 조회
    
    Learning Agent 분석용 데이터
    """
    agent = LearningAgent(db)
    pairs = agent.collect_edit_pairs(
        property_code=property_code,
        limit=limit,
        only_sent=True,
    )
    
    return {
        "count": len(pairs),
        "pairs": [
            {
                "draft_id": p.draft_id,
                "conversation_id": p.conversation_id,
                "property_code": p.property_code,
                "original": p.original[:500] if p.original else None,
                "edited": p.edited[:500] if p.edited else None,
                "guest_message": p.guest_message[:300] if p.guest_message else None,
                "created_at": p.created_at.isoformat(),
                "was_sent": p.was_sent,
            }
            for p in pairs
        ]
    }


@router.post("/analyze-patterns")
async def analyze_patterns(
    property_code: Optional[str] = Query(None),
    limit: int = Query(100, ge=10, le=300),
    db: Session = Depends(get_db),
):
    """
    수정 패턴 분석 (LLM 활용)
    
    원본-수정 쌍을 분석하여 공통 패턴 발견
    """
    agent = LearningAgent(db)
    
    # 데이터 수집
    pairs = agent.collect_edit_pairs(
        property_code=property_code,
        limit=limit,
        only_sent=True,
    )
    
    if len(pairs) < 5:
        return {
            "error": "Not enough data",
            "message": f"최소 5건 이상의 수정 데이터가 필요합니다. (현재: {len(pairs)}건)",
            "pairs_count": len(pairs),
        }
    
    # 패턴 분석
    patterns = await agent.analyze_patterns(pairs)
    
    return {
        "pairs_analyzed": len(pairs),
        "patterns_found": len(patterns),
        "patterns": [
            {
                "type": p.pattern_type,
                "description": p.description,
                "frequency": p.frequency,
                "confidence": p.confidence,
                "examples": p.examples[:3],
            }
            for p in patterns
        ]
    }


@router.get("/style-profile/{property_code}")
async def get_style_profile(
    property_code: str,
    db: Session = Depends(get_db),
):
    """
    숙소별 스타일 프로필 생성
    
    호스트의 수정 패턴을 분석하여 스타일 프로필 생성
    Draft Agent가 참고할 수 있는 컨텍스트 포함
    """
    agent = LearningAgent(db)
    profile = await agent.generate_style_profile(property_code=property_code)
    
    if not profile:
        return {
            "error": "Not enough data",
            "message": f"숙소 {property_code}에 대한 수정 데이터가 부족합니다.",
        }
    
    return {
        "profile": profile.to_dict(),
        "prompt_context": profile.to_prompt_context(),
    }


@router.post("/full-report")
async def generate_full_report(
    db: Session = Depends(get_db),
):
    """
    전체 분석 리포트 생성
    
    - 전체 통계
    - 패턴 분석
    - 숙소별 스타일 프로필
    - 개선 권장사항
    
    ⚠️ 시간이 오래 걸릴 수 있음 (30초~1분)
    """
    agent = LearningAgent(db)
    report = await agent.generate_full_report()
    
    return report


# Integer import for SQLAlchemy cast
from sqlalchemy import Integer
