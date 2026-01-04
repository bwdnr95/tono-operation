# backend/app/services/style_profile_integration.py
"""
Draft Agent에 스타일 프로필 통합 예시

AutoReplyService._build_conversation_context()에 추가할 코드
"""

# ═══════════════════════════════════════════════════════════════
# Option 1: 간단한 통합 (캐시 없음)
# ═══════════════════════════════════════════════════════════════

def _build_conversation_context_with_style(
    self,
    *,
    message_id: int,
    airbnb_thread_id: str,
    property_code: str,
) -> Dict[str, Any]:
    """
    기존 컨텍스트 + 스타일 프로필 추가
    """
    # 기존 컨텍스트 빌드
    context = self._build_conversation_context(
        message_id=message_id,
        airbnb_thread_id=airbnb_thread_id,
        property_code=property_code,
    )
    
    # 스타일 프로필 추가 (있으면)
    try:
        from app.services.learning_agent import LearningAgent
        import asyncio
        
        agent = LearningAgent(self._db, openai_client=self._client)
        
        # 동기 컨텍스트에서 비동기 호출
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 이벤트 루프가 실행 중이면 새 스레드에서 실행
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    agent.generate_style_profile(property_code=property_code)
                )
                profile = future.result(timeout=10)
        else:
            profile = asyncio.run(
                agent.generate_style_profile(property_code=property_code)
            )
        
        if profile:
            context["style_profile"] = profile.to_prompt_context()
    except Exception as e:
        # 스타일 프로필 실패해도 기본 동작은 유지
        logger.warning(f"Style profile generation failed: {e}")
    
    return context


# ═══════════════════════════════════════════════════════════════
# Option 2: 캐시된 스타일 프로필 사용 (권장)
# ═══════════════════════════════════════════════════════════════

"""
PropertyProfile 테이블에 style_profile JSONB 컬럼 추가하고,
Learning Agent가 주기적으로 업데이트하는 방식

ALTER TABLE property_profiles 
ADD COLUMN style_profile JSONB;

그러면 context 빌드 시:
"""

def _build_conversation_context_with_cached_style(
    self,
    *,
    message_id: int,
    airbnb_thread_id: str,
    property_code: str,
) -> Dict[str, Any]:
    """
    캐시된 스타일 프로필 사용 (DB에서 조회)
    """
    context = self._build_conversation_context(
        message_id=message_id,
        airbnb_thread_id=airbnb_thread_id,
        property_code=property_code,
    )
    
    # PropertyProfile에서 캐시된 스타일 프로필 조회
    profile = self._property_repo.get_by_property_code(property_code)
    if profile and hasattr(profile, 'style_profile') and profile.style_profile:
        # 스타일 프로필을 프롬프트 컨텍스트로 변환
        sp = profile.style_profile
        context["style_profile"] = f"""[호스트 스타일 프로필]
톤: {sp.get('tone', 'friendly')}
문장 종결: {', '.join(sp.get('sentence_endings', [])[:5])}
인사 스타일: {sp.get('greeting_style', '')}
이모지 사용: {sp.get('emoji_usage', 'minimal')}
"""
        
        # Few-shot 예시 추가
        if sp.get('few_shot_examples'):
            examples = sp['few_shot_examples'][:3]
            context["style_examples"] = examples
    
    return context


# ═══════════════════════════════════════════════════════════════
# System Prompt에 스타일 프로필 추가
# ═══════════════════════════════════════════════════════════════

"""
_build_user_prompt()에서 style_profile 섹션 추가:
"""

def _build_user_prompt_with_style(self, guest_message: str, context: Dict[str, Any]) -> str:
    """
    User Prompt에 스타일 프로필 섹션 추가
    """
    # ... 기존 섹션들 ...
    
    # 스타일 프로필 섹션 추가
    style_section = ""
    if context.get("style_profile"):
        style_section = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎨 호스트 스타일 (이 스타일로 답변하세요)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{context['style_profile']}
"""
    
    # Few-shot 예시 섹션
    examples_section = ""
    if context.get("style_examples"):
        lines = ["\n[이 호스트의 실제 답변 예시 - 이 톤을 참고하세요]"]
        for i, ex in enumerate(context["style_examples"], 1):
            lines.append(f"게스트: {ex.get('guest', '')[:100]}")
            lines.append(f"호스트: {ex.get('host', '')[:200]}")
            lines.append("")
        examples_section = "\n".join(lines)
    
    # 최종 조립
    return f"""{target_section}
{style_section}
{examples_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 참고 정보
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{history_section}{commitment_section}{reservation_section}{property_section}{faq_section}{closing_hint}
"""


# ═══════════════════════════════════════════════════════════════
# 스케줄러로 스타일 프로필 주기적 업데이트
# ═══════════════════════════════════════════════════════════════

"""
scheduler.py에 추가:

async def style_profile_update_job():
    '''매일 새벽 3시에 스타일 프로필 업데이트'''
    from app.db.session import SessionLocal
    from app.services.learning_agent import LearningAgent
    from app.repositories.property_profile_repository import PropertyProfileRepository
    
    db = SessionLocal()
    try:
        agent = LearningAgent(db)
        prop_repo = PropertyProfileRepository(db)
        
        # 모든 활성 숙소 조회
        properties = prop_repo.get_all_active()
        
        for prop in properties:
            try:
                profile = await agent.generate_style_profile(
                    property_code=prop.property_code
                )
                if profile:
                    # DB에 캐시
                    prop.style_profile = profile.to_dict()
                    db.add(prop)
            except Exception as e:
                logger.warning(f"Style profile update failed for {prop.property_code}: {e}")
        
        db.commit()
        logger.info(f"Style profiles updated for {len(properties)} properties")
    finally:
        db.close()

# 스케줄러 등록
_scheduler.add_job(
    style_profile_update_job,
    trigger=CronTrigger(hour=3, minute=0, timezone="Asia/Seoul"),
    id="style_profile_update_job",
    name="스타일 프로필 업데이트",
    replace_existing=True,
)
"""
