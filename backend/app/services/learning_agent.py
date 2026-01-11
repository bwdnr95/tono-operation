# backend/app/services/learning_agent.py
"""
Learning Agent: 호스트 수정 데이터 분석 및 스타일 프로필 생성

목적:
1. 수정된 draft_replies 분석하여 패턴 발견
2. 호스트별/숙소별 스타일 프로필 생성
3. Draft Agent가 참고할 수 있는 형태로 출력

설계 원칙:
- 데이터 기반 자동 분석 (수동 분류 없음)
- LLM으로 패턴 해석 및 프로필 생성
- 점진적 개선 가능한 구조
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class EditPair:
    """원본-수정 쌍"""
    draft_id: str
    conversation_id: str
    airbnb_thread_id: str
    property_code: Optional[str]
    
    original: str           # AI 원본
    edited: str             # 호스트 수정본
    guest_message: Optional[str]  # 게스트 메시지 (있으면)
    
    created_at: datetime
    was_sent: bool          # 발송 여부


@dataclass
class EditPattern:
    """발견된 수정 패턴"""
    pattern_type: str       # tone_change, info_add, info_remove, structure_change, etc.
    description: str        # 패턴 설명
    frequency: int          # 발생 빈도
    examples: List[Dict[str, str]]  # 예시 목록 [{original, edited}]
    confidence: float       # 패턴 신뢰도 (0~1)


@dataclass
class StyleProfile:
    """호스트/숙소 스타일 프로필"""
    profile_id: str         # property_code 또는 host_id
    profile_type: str       # "property" 또는 "host"
    
    # 톤 특성
    tone: str               # formal, casual, friendly, etc.
    sentence_endings: List[str]  # 자주 쓰는 문장 종결 표현
    greeting_style: str     # 인사 스타일
    emoji_usage: str        # none, minimal, moderate, frequent
    
    # 내용 특성
    common_additions: List[str]  # 자주 추가하는 정보
    common_removals: List[str]   # 자주 삭제하는 정보
    
    # 메타
    sample_count: int       # 분석에 사용된 샘플 수
    generated_at: datetime
    
    # Few-shot 예시
    few_shot_examples: List[Dict[str, str]] = field(default_factory=list)
    
    def to_prompt_context(self) -> str:
        """Draft Agent 프롬프트에 주입할 컨텍스트 생성"""
        lines = [
            f"[호스트 스타일 프로필]",
            f"톤: {self.tone}",
            f"문장 종결: {', '.join(self.sentence_endings[:5])}",
            f"인사 스타일: {self.greeting_style}",
            f"이모지 사용: {self.emoji_usage}",
        ]
        
        if self.common_additions:
            lines.append(f"자주 추가하는 정보: {', '.join(self.common_additions[:3])}")
        
        if self.few_shot_examples:
            lines.append("\n[이 호스트의 답변 예시]")
            for i, ex in enumerate(self.few_shot_examples[:3], 1):
                lines.append(f"예시 {i}:")
                lines.append(f"  게스트: {ex.get('guest', 'N/A')[:100]}")
                lines.append(f"  호스트: {ex.get('host', 'N/A')[:200]}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_type": self.profile_type,
            "tone": self.tone,
            "sentence_endings": self.sentence_endings,
            "greeting_style": self.greeting_style,
            "emoji_usage": self.emoji_usage,
            "common_additions": self.common_additions,
            "common_removals": self.common_removals,
            "sample_count": self.sample_count,
            "generated_at": self.generated_at.isoformat(),
            "few_shot_examples": self.few_shot_examples,
        }


# ═══════════════════════════════════════════════════════════════
# Learning Agent
# ═══════════════════════════════════════════════════════════════

class LearningAgent:
    """
    호스트 수정 데이터 분석 및 스타일 프로필 생성
    
    사용법:
        agent = LearningAgent(db, openai_client)
        
        # 수정 데이터 수집
        edit_pairs = agent.collect_edit_pairs()
        
        # 패턴 분석
        patterns = await agent.analyze_patterns(edit_pairs)
        
        # 스타일 프로필 생성
        profile = await agent.generate_style_profile(
            property_code="2A31",
            edit_pairs=edit_pairs
        )
    """
    
    def __init__(self, db: Session, openai_client=None):
        self._db = db
        self._openai_client = openai_client
        
        if not openai_client:
            from app.adapters.llm_client import get_openai_client
            self._openai_client = get_openai_client()
    
    # ═══════════════════════════════════════════════════════════
    # Step 1: 데이터 수집
    # ═══════════════════════════════════════════════════════════
    
    def collect_edit_pairs(
        self,
        *,
        property_code: Optional[str] = None,
        limit: int = 500,
        only_sent: bool = True,
    ) -> List[EditPair]:
        """
        수정된 draft_replies에서 원본-수정 쌍 수집
        
        Args:
            property_code: 특정 숙소만 필터링 (선택)
            limit: 최대 수집 건수
            only_sent: 발송된 것만 수집 (권장)
        """
        from app.domain.models.conversation import DraftReply, Conversation, SendActionLog, SendAction
        
        # 수정된 draft 조회
        query = (
            select(DraftReply, Conversation)
            .join(Conversation, DraftReply.conversation_id == Conversation.id)
            .where(DraftReply.is_edited == True)
            .where(DraftReply.original_content.isnot(None))
        )
        
        if property_code:
            query = query.where(Conversation.property_code == property_code)
        
        query = query.order_by(DraftReply.created_at.desc()).limit(limit)
        
        results = self._db.execute(query).all()
        
        edit_pairs = []
        for draft, conv in results:
            # 발송 여부 확인
            was_sent = False
            if only_sent:
                sent_log = self._db.execute(
                    select(SendActionLog)
                    .where(SendActionLog.conversation_id == conv.id)
                    .where(SendActionLog.action == SendAction.send)
                    .limit(1)
                ).scalar_one_or_none()
                was_sent = sent_log is not None
                
                if only_sent and not was_sent:
                    continue
            
            # ✅ v5: 스냅샷 우선 사용, 없으면 시간 기반 조회 (마이그레이션 안 된 데이터 대응)
            guest_message = draft.guest_message_snapshot
            if not guest_message:
                guest_message = self._get_guest_message_at_draft_time(
                    conv.airbnb_thread_id, 
                    draft.created_at
                )
            
            # property_code는 reservation_info에서 조회 (Single Source of Truth)
            from app.services.property_resolver import get_effective_property_code
            effective_property_code = get_effective_property_code(self._db, conv.airbnb_thread_id)
            
            edit_pairs.append(EditPair(
                draft_id=str(draft.id),
                conversation_id=str(conv.id),
                airbnb_thread_id=conv.airbnb_thread_id,
                property_code=effective_property_code,  # reservation_info 기반
                original=draft.original_content,
                edited=draft.content,
                guest_message=guest_message,
                created_at=draft.created_at,
                was_sent=was_sent,
            ))
        
        logger.info(f"LEARNING_AGENT: Collected {len(edit_pairs)} edit pairs")
        return edit_pairs
    
    def _get_guest_message_at_draft_time(
        self, 
        airbnb_thread_id: str, 
        draft_created_at: datetime
    ) -> Optional[str]:
        """Draft 생성 시점 직전의 게스트 메시지 조회 (마이그레이션 안 된 데이터용)"""
        from app.domain.models.incoming_message import IncomingMessage, MessageDirection
        
        msg = self._db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
            .where(IncomingMessage.direction == MessageDirection.incoming)
            .where(IncomingMessage.received_at < draft_created_at)  # Draft 이전 메시지만
            .order_by(IncomingMessage.received_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        return msg.pure_guest_message if msg else None
    
    def _get_latest_guest_message(self, airbnb_thread_id: str) -> Optional[str]:
        """게스트 최신 메시지 조회 (deprecated - _get_guest_message_at_draft_time 사용 권장)"""
        from app.domain.models.incoming_message import IncomingMessage, MessageDirection
        
        msg = self._db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
            .where(IncomingMessage.direction == MessageDirection.incoming)
            .order_by(IncomingMessage.received_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        return msg.pure_guest_message if msg else None
    
    # ═══════════════════════════════════════════════════════════
    # Step 2: 패턴 분석
    # ═══════════════════════════════════════════════════════════
    
    async def analyze_patterns(
        self,
        edit_pairs: List[EditPair],
    ) -> List[EditPattern]:
        """
        수정 패턴 자동 분석 (LLM 활용)
        
        LLM이 원본-수정 쌍을 분석하여:
        - 어떤 유형의 수정인지 분류
        - 공통 패턴 발견
        - 패턴별 빈도 계산
        """
        if not edit_pairs:
            return []
        
        # 샘플링 (너무 많으면 비용 문제)
        samples = edit_pairs[:30] if len(edit_pairs) > 30 else edit_pairs
        
        # LLM에게 분석 요청
        analysis_prompt = self._build_pattern_analysis_prompt(samples)
        
        try:
            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._get_pattern_analysis_system_prompt()},
                    {"role": "user", "content": analysis_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2000,
            )
            
            result = json.loads(response.choices[0].message.content)
            patterns = self._parse_pattern_analysis(result, edit_pairs)
            
            logger.info(f"LEARNING_AGENT: Found {len(patterns)} patterns")
            return patterns
            
        except Exception as e:
            logger.error(f"LEARNING_AGENT: Pattern analysis failed - {e}")
            return []
    
    def _get_pattern_analysis_system_prompt(self) -> str:
        return """너는 숙박업 호스트의 메시지 수정 패턴을 분석하는 전문가다.

AI가 생성한 원본과 호스트가 수정한 버전을 비교하여:
1. 수정 유형 분류
2. 공통 패턴 발견
3. 패턴별 빈도 추정

수정 유형:
- tone_change: 말투/톤 변경 (~입니다 → ~예요)
- info_add: 정보 추가
- info_remove: 불필요한 내용 삭제
- greeting_change: 인사 방식 변경
- emoji_change: 이모지 추가/삭제
- structure_change: 문장 구조 변경
- complete_rewrite: 완전히 다시 작성

OUTPUT FORMAT (JSON):
{
  "patterns": [
    {
      "pattern_type": "tone_change",
      "description": "~입니다/~합니다 종결을 ~예요/~에요로 변경",
      "frequency_percent": 45,
      "examples": [
        {"original": "체크인은 15시입니다.", "edited": "체크인은 3시예요~"}
      ],
      "confidence": 0.9
    }
  ],
  "overall_insights": "전반적으로 딱딱한 톤을 부드럽게 바꾸는 경향이 강함"
}"""
    
    def _build_pattern_analysis_prompt(self, samples: List[EditPair]) -> str:
        lines = ["다음은 AI 원본과 호스트 수정본 쌍입니다. 패턴을 분석하세요.\n"]
        
        for i, pair in enumerate(samples, 1):
            lines.append(f"=== 케이스 {i} ===")
            if pair.guest_message:
                lines.append(f"게스트: {pair.guest_message[:200]}")
            lines.append(f"AI 원본: {pair.original[:300]}")
            lines.append(f"호스트 수정: {pair.edited[:300]}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _parse_pattern_analysis(
        self, 
        result: Dict[str, Any],
        all_pairs: List[EditPair],
    ) -> List[EditPattern]:
        """LLM 분석 결과 파싱"""
        patterns = []
        
        for p in result.get("patterns", []):
            patterns.append(EditPattern(
                pattern_type=p.get("pattern_type", "unknown"),
                description=p.get("description", ""),
                frequency=int(len(all_pairs) * p.get("frequency_percent", 0) / 100),
                examples=p.get("examples", []),
                confidence=p.get("confidence", 0.5),
            ))
        
        return patterns
    
    # ═══════════════════════════════════════════════════════════
    # Step 3: 스타일 프로필 생성
    # ═══════════════════════════════════════════════════════════
    
    async def generate_style_profile(
        self,
        *,
        property_code: str,
        edit_pairs: Optional[List[EditPair]] = None,
    ) -> Optional[StyleProfile]:
        """
        숙소별 스타일 프로필 생성
        
        Args:
            property_code: 숙소 코드
            edit_pairs: 미리 수집된 데이터 (없으면 자동 수집)
        """
        # 데이터 수집
        if edit_pairs is None:
            edit_pairs = self.collect_edit_pairs(
                property_code=property_code,
                limit=100,
                only_sent=True,
            )
        else:
            # 해당 숙소만 필터링
            edit_pairs = [p for p in edit_pairs if p.property_code == property_code]
        
        if len(edit_pairs) < 3:
            logger.warning(f"LEARNING_AGENT: Not enough data for {property_code} ({len(edit_pairs)} pairs)")
            return None
        
        # LLM으로 스타일 분석
        profile_prompt = self._build_profile_prompt(edit_pairs)
        
        try:
            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._get_profile_system_prompt()},
                    {"role": "user", "content": profile_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1500,
            )
            
            result = json.loads(response.choices[0].message.content)
            profile = self._parse_profile_result(result, property_code, edit_pairs)
            
            logger.info(f"LEARNING_AGENT: Generated style profile for {property_code}")
            return profile
            
        except Exception as e:
            logger.error(f"LEARNING_AGENT: Profile generation failed - {e}")
            return None
    
    def _get_profile_system_prompt(self) -> str:
        return """너는 숙박업 호스트의 커뮤니케이션 스타일을 분석하는 전문가다.

호스트가 수정한 메시지들을 분석하여 스타일 프로필을 생성한다.

분석 항목:
1. 톤 (formal/casual/friendly/professional)
2. 문장 종결 표현 (~입니다, ~예요, ~요 등)
3. 인사 스타일 (안녕하세요!, 네!, 앗! 등)
4. 이모지 사용 빈도 (none/minimal/moderate/frequent)
5. 자주 추가하는 정보
6. 자주 삭제하는 정보

OUTPUT FORMAT (JSON):
{
  "tone": "friendly",
  "sentence_endings": ["~예요", "~에요", "~요"],
  "greeting_style": "짧고 친근한 인사 (안녕하세요!, 네!)",
  "emoji_usage": "moderate",
  "common_additions": ["체크인 시간 강조", "연락처 안내"],
  "common_removals": ["형식적인 문구", "중복 설명"],
  "style_summary": "친근하고 간결한 스타일. 이모지를 적절히 사용하며 핵심 정보 위주로 전달."
}"""
    
    def _build_profile_prompt(self, edit_pairs: List[EditPair]) -> str:
        lines = ["다음은 이 호스트가 수정한 메시지들입니다. 스타일을 분석하세요.\n"]
        
        # 수정본만 분석 (호스트의 최종 스타일)
        for i, pair in enumerate(edit_pairs[:20], 1):
            lines.append(f"=== 메시지 {i} ===")
            if pair.guest_message:
                lines.append(f"게스트 질문: {pair.guest_message[:150]}")
            lines.append(f"호스트 답변: {pair.edited[:300]}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _parse_profile_result(
        self,
        result: Dict[str, Any],
        property_code: str,
        edit_pairs: List[EditPair],
    ) -> StyleProfile:
        """LLM 결과 파싱하여 StyleProfile 생성"""
        
        # Few-shot 예시 추출 (좋은 답변들)
        few_shots = []
        for pair in edit_pairs[:5]:
            if pair.guest_message and pair.edited:
                few_shots.append({
                    "guest": pair.guest_message[:200],
                    "host": pair.edited[:400],
                })
        
        return StyleProfile(
            profile_id=property_code,
            profile_type="property",
            tone=result.get("tone", "friendly"),
            sentence_endings=result.get("sentence_endings", []),
            greeting_style=result.get("greeting_style", ""),
            emoji_usage=result.get("emoji_usage", "minimal"),
            common_additions=result.get("common_additions", []),
            common_removals=result.get("common_removals", []),
            sample_count=len(edit_pairs),
            generated_at=datetime.utcnow(),
            few_shot_examples=few_shots,
        )
    
    # ═══════════════════════════════════════════════════════════
    # Step 4: 전체 분석 리포트
    # ═══════════════════════════════════════════════════════════
    
    async def generate_full_report(self) -> Dict[str, Any]:
        """
        전체 데이터 분석 리포트 생성
        
        Returns:
            {
                "summary": {...},
                "patterns": [...],
                "profiles_by_property": {...},
                "recommendations": [...]
            }
        """
        # 전체 데이터 수집
        all_pairs = self.collect_edit_pairs(limit=500, only_sent=True)
        
        if not all_pairs:
            return {"error": "No edit data available"}
        
        # 기본 통계
        total_count = len(all_pairs)
        properties = set(p.property_code for p in all_pairs if p.property_code)
        
        # 패턴 분석
        patterns = await self.analyze_patterns(all_pairs)
        
        # 숙소별 프로필 생성
        profiles = {}
        for prop in properties:
            profile = await self.generate_style_profile(
                property_code=prop,
                edit_pairs=all_pairs,
            )
            if profile:
                profiles[prop] = profile.to_dict()
        
        # 개선 권장사항 생성
        recommendations = self._generate_recommendations(patterns)
        
        return {
            "summary": {
                "total_edits": total_count,
                "properties_analyzed": len(properties),
                "patterns_found": len(patterns),
                "generated_at": datetime.utcnow().isoformat(),
            },
            "patterns": [
                {
                    "type": p.pattern_type,
                    "description": p.description,
                    "frequency": p.frequency,
                    "confidence": p.confidence,
                    "examples": p.examples[:2],
                }
                for p in patterns
            ],
            "profiles_by_property": profiles,
            "recommendations": recommendations,
        }
    
    def _generate_recommendations(self, patterns: List[EditPattern]) -> List[str]:
        """패턴 기반 개선 권장사항 생성"""
        recommendations = []
        
        for p in patterns:
            if p.confidence >= 0.7 and p.frequency >= 5:
                if p.pattern_type == "tone_change":
                    recommendations.append(
                        f"톤 개선 필요: {p.description} (빈도: {p.frequency}건)"
                    )
                elif p.pattern_type == "info_add":
                    recommendations.append(
                        f"정보 추가 필요: {p.description} (빈도: {p.frequency}건)"
                    )
                elif p.pattern_type == "complete_rewrite":
                    recommendations.append(
                        f"⚠️ 완전 재작성 빈번: AI가 맥락을 자주 놓침 (빈도: {p.frequency}건)"
                    )
        
        return recommendations


# ═══════════════════════════════════════════════════════════════
# 편의 함수
# ═══════════════════════════════════════════════════════════════

async def run_learning_analysis(db: Session) -> Dict[str, Any]:
    """
    Learning Agent 실행하여 전체 분석 리포트 생성
    
    사용법:
        from app.services.learning_agent import run_learning_analysis
        report = await run_learning_analysis(db)
    """
    agent = LearningAgent(db)
    return await agent.generate_full_report()


def get_style_profile_for_property(
    db: Session,
    property_code: str,
) -> Optional[Dict[str, Any]]:
    """
    숙소별 스타일 프로필 조회 (캐시된 것 또는 새로 생성)
    
    TODO: 프로필 캐싱 (DB 또는 Redis)
    """
    import asyncio
    
    agent = LearningAgent(db)
    profile = asyncio.run(agent.generate_style_profile(property_code=property_code))
    
    return profile.to_dict() if profile else None
