# backend/app/services/scheduler.py
"""
TONO Scheduler Service (APScheduler 기반)

5분마다 Gmail Ingest + Draft 생성 + Orchestrator 판단을 실행합니다.

**중요**: 무거운 작업은 별도 스레드에서 실행하여 
FastAPI event loop를 블로킹하지 않습니다.

v2 변경사항:
- Orchestrator 연동 추가
- AUTO_SEND 시 자동 발송 기능 추가
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# 스케줄러 전용 Thread Pool (최대 3개 스레드 - Gmail, iCal 동시 실행 대비)
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="tono_scheduler_")

# 로거 설정
logger = logging.getLogger("tono.scheduler")
logger.setLevel(logging.INFO)

# 콘솔 핸들러 추가 (서버 로그에 출력)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [SCHEDULER] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# 전역 스케줄러 인스턴스
_scheduler: Optional[AsyncIOScheduler] = None

# Job 실행 중 플래그 (중복 실행 방지)
_job_running: bool = False


async def gmail_ingest_job():
    """
    Gmail Ingest Job (비동기 wrapper)
    
    실제 작업은 별도 스레드에서 실행하여 
    FastAPI event loop를 블로킹하지 않습니다.
    
    🆕 fire-and-forget 방식: await 없이 스레드에 위임하고 즉시 반환
    """
    global _job_running
    
    # 이미 실행 중이면 스킵
    if _job_running:
        logger.warning("Gmail Ingest Job 스킵 - 이전 Job이 아직 실행 중")
        return
    
    _job_running = True
    logger.info("Gmail Ingest Job 시작 (별도 스레드로 위임)")
    
    # 🆕 fire-and-forget: 스레드풀에 제출하고 즉시 반환
    # 스레드 작업 완료 후 플래그 해제는 스레드 내에서 처리
    _executor.submit(_gmail_ingest_sync_with_flag)


# iCal 동기화 Job 실행 중 플래그
_ical_job_running: bool = False

# Daily Reminder Job 실행 중 플래그
_daily_job_running: bool = False

# Property FAQ Stats Job 실행 중 플래그
_faq_stats_job_running: bool = False


async def property_faq_stats_job():
    """
    Property FAQ 통계 집계 Job (매일 새벽 2시)
    
    draft_replies 데이터 기반으로 property + faq_key별 승인률 집계
    """
    global _faq_stats_job_running
    
    if _faq_stats_job_running:
        logger.warning("Property FAQ Stats Job 스킵 - 이전 Job이 아직 실행 중")
        return
    
    _faq_stats_job_running = True
    logger.info("Property FAQ Stats Job 시작 (별도 스레드로 위임)")
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _property_faq_stats_sync)
    finally:
        _faq_stats_job_running = False
        logger.info("Property FAQ Stats Job 완료 (플래그 해제)")


def _property_faq_stats_sync():
    """Property FAQ Stats 실제 작업 (별도 스레드에서 실행)"""
    from app.db.session import SessionLocal
    from sqlalchemy import text
    import traceback
    
    db = SessionLocal()
    started_at = datetime.utcnow()
    
    try:
        # 통계 집계 SQL (used_faq_keys 비어있으면 response_outcome 사용)
        stats_sql = """
        WITH draft_stats AS (
            -- 1. used_faq_keys가 있는 경우
            SELECT 
                c.property_code,
                jsonb_array_elements_text(dr.outcome_label->'used_faq_keys') as faq_key,
                dr.is_edited,
                dr.updated_at
            FROM draft_replies dr
            JOIN conversations c ON dr.conversation_id = c.id
            WHERE dr.outcome_label IS NOT NULL
              AND dr.outcome_label->'used_faq_keys' IS NOT NULL
              AND jsonb_array_length(dr.outcome_label->'used_faq_keys') > 0
              AND c.property_code IS NOT NULL
            
            UNION ALL
            
            -- 2. used_faq_keys가 비어있으면 response_outcome 사용
            SELECT 
                c.property_code,
                dr.outcome_label->>'response_outcome' as faq_key,
                dr.is_edited,
                dr.updated_at
            FROM draft_replies dr
            JOIN conversations c ON dr.conversation_id = c.id
            WHERE dr.outcome_label IS NOT NULL
              AND (dr.outcome_label->'used_faq_keys' IS NULL 
                   OR jsonb_array_length(dr.outcome_label->'used_faq_keys') = 0)
              AND dr.outcome_label->>'response_outcome' IS NOT NULL
              AND c.property_code IS NOT NULL
        ),
        aggregated AS (
            SELECT 
                property_code,
                faq_key,
                COUNT(*) as total_count,
                COUNT(*) FILTER (WHERE is_edited = false OR is_edited IS NULL) as approved_count,
                COUNT(*) FILTER (WHERE is_edited = true) as edited_count,
                MAX(updated_at) FILTER (WHERE is_edited = false OR is_edited IS NULL) as last_approved_at,
                MAX(updated_at) FILTER (WHERE is_edited = true) as last_edited_at
            FROM draft_stats
            WHERE faq_key IS NOT NULL AND faq_key != ''
            GROUP BY property_code, faq_key
        )
        INSERT INTO property_faq_auto_send_stats (
            property_code, faq_key, total_count, approved_count, edited_count,
            approval_rate, eligible_for_auto_send, last_approved_at, last_edited_at, updated_at
        )
        SELECT 
            property_code, faq_key, total_count, approved_count, edited_count,
            CASE WHEN total_count > 0 THEN approved_count::float / total_count ELSE 0 END,
            CASE WHEN total_count >= 5 AND (approved_count::float / NULLIF(total_count, 0)) >= 0.8 THEN TRUE ELSE FALSE END,
            last_approved_at, last_edited_at, NOW()
        FROM aggregated
        ON CONFLICT (property_code, faq_key) DO UPDATE SET
            total_count = EXCLUDED.total_count,
            approved_count = EXCLUDED.approved_count,
            edited_count = EXCLUDED.edited_count,
            approval_rate = EXCLUDED.approval_rate,
            eligible_for_auto_send = EXCLUDED.eligible_for_auto_send,
            last_approved_at = EXCLUDED.last_approved_at,
            last_edited_at = EXCLUDED.last_edited_at,
            updated_at = NOW();
        """
        
        db.execute(text(stats_sql))
        
        # 결과 요약
        result = db.execute(text("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE eligible_for_auto_send), COUNT(DISTINCT property_code)
            FROM property_faq_auto_send_stats
        """)).fetchone()
        
        db.commit()
        
        duration = (datetime.utcnow() - started_at).total_seconds()
        logger.info(
            f"Property FAQ Stats Job 완료: {duration:.2f}s, "
            f"records={result[0]}, eligible={result[1]}, properties={result[2]}"
        )
        
        # 배치 로그 저장
        _log_batch_result(db, "property_faq_stats", "SUCCESS", started_at, duration, {
            "total_records": result[0],
            "eligible_count": result[1],
            "property_count": result[2],
        })
        
    except Exception as e:
        duration = (datetime.utcnow() - started_at).total_seconds()
        error_msg = str(e)
        error_tb = traceback.format_exc()
        
        logger.error(f"Property FAQ Stats Job 실패: {error_msg}")
        logger.error(error_tb)
        db.rollback()
        
        # 배치 로그 저장
        _log_batch_result(db, "property_faq_stats", "FAILED", started_at, duration, None, error_msg)
        
        # Slack 알림
        _send_batch_slack_alert("property_faq_stats", error_msg)
        
    finally:
        db.close()


def _log_batch_result(db, job_name: str, status: str, started_at, duration: float, summary: dict = None, error: str = None):
    """배치 결과 로그 저장"""
    from sqlalchemy import text
    import json
    
    try:
        # 테이블 없으면 생성
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS batch_job_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_name VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ,
                duration_seconds FLOAT,
                result_summary JSONB,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        
        db.execute(text("""
            INSERT INTO batch_job_logs (job_name, status, started_at, finished_at, duration_seconds, result_summary, error_message)
            VALUES (:job_name, :status, :started_at, :finished_at, :duration, :summary, :error)
        """), {
            "job_name": job_name,
            "status": status,
            "started_at": started_at,
            "finished_at": datetime.utcnow(),
            "duration": duration,
            "summary": json.dumps(summary) if summary else None,
            "error": error,
        })
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log batch result: {e}")


def _send_batch_slack_alert(job_name: str, error_msg: str):
    """Slack 알림 전송"""
    from app.core.config import settings
    
    slack_webhook = getattr(settings, 'SLACK_WEBHOOK_URL', None)
    if not slack_webhook:
        return
    
    try:
        import httpx
        httpx.post(slack_webhook, json={
            "text": f"🚨 *[TONO] 배치 작업 실패*\n*Job:* `{job_name}`\n*Error:* {error_msg}"
        }, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to send Slack alert: {e}")


async def daily_reminder_job():
    """
    일일 리마인더 Job (매일 오전 9시)
    - OC 리마인더
    - 당일 체크인 알림
    """
    global _daily_job_running
    
    if _daily_job_running:
        logger.warning("Daily Reminder Job 스킵 - 이전 Job이 아직 실행 중")
        return
    
    _daily_job_running = True
    logger.info("Daily Reminder Job 시작 (별도 스레드로 위임)")
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _daily_reminder_sync)
    finally:
        _daily_job_running = False
        logger.info("Daily Reminder Job 완료 (플래그 해제)")


def _daily_reminder_sync():
    """Daily Reminder 실제 작업 (별도 스레드에서 실행)"""
    from app.db.session import SessionLocal
    from app.services.notification_service import NotificationService
    from app.domain.models.staff_notification import StaffNotification
    from app.domain.models.reservation_info import ReservationInfo
    from sqlalchemy import select
    from datetime import date
    
    db = SessionLocal()
    try:
        today = date.today()
        notification_svc = NotificationService(db)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. OC 리마인더: 오늘 처리해야 할 OC 건수
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        try:
            oc_stmt = (
                select(StaffNotification)
                .where(StaffNotification.priority_date == today)
                .where(StaffNotification.status.in_(["pending", "acknowledged"]))
            )
            oc_items = db.execute(oc_stmt).scalars().all()
            
            if oc_items:
                oc_data = [
                    {"property_code": oc.property_code, "action": oc.action}
                    for oc in oc_items
                ]
                result = notification_svc.create_oc_reminder(
                    oc_count=len(oc_items),
                    oc_items=oc_data,
                )
                if result:
                    logger.info(f"OC 리마인더 생성: {len(oc_items)}건")
        except Exception as e:
            logger.warning(f"Failed to create OC reminder: {e}")
        
        db.commit()
        logger.info("Daily Reminder Job 처리 완료")
        
    except Exception as e:
        logger.error(f"Daily Reminder Job 실패: {e}")
        db.rollback()
    finally:
        db.close()


async def ical_sync_job():
    """
    iCal 동기화 Job (30분 간격)
    
    모든 property의 iCal을 fetch하여 blocked_dates 업데이트
    실제 작업은 별도 스레드에서 실행
    """
    global _ical_job_running
    
    if _ical_job_running:
        logger.warning("iCal Sync Job 스킵 - 이전 Job이 아직 실행 중")
        return
    
    _ical_job_running = True
    logger.info("iCal Sync Job 시작 (별도 스레드로 위임)")
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _ical_sync_sync)
    finally:
        _ical_job_running = False
        logger.info("iCal Sync Job 완료 (플래그 해제)")


def _ical_sync_sync():
    """
    iCal 동기화 실제 작업 (별도 스레드에서 실행)
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_ical_sync_async())
    finally:
        loop.close()


async def _ical_sync_async():
    """iCal 동기화 비동기 작업 (실제 로직)"""
    from app.db.session import SessionLocal
    from app.services.ical_service import IcalService
    
    db = SessionLocal()
    try:
        service = IcalService(db)
        results = await service.sync_all()
        db.commit()
        
        total_synced = sum(results.values())
        logger.info(
            f"iCal Sync Job 완료: {len(results)}개 숙소, "
            f"총 {total_synced}개 차단일 동기화"
        )
        for prop_code, count in results.items():
            logger.debug(f"  {prop_code}: {count}개")
            
    except Exception as e:
        logger.error(f"iCal Sync Job 실패: {e}")
        db.rollback()
    finally:
        db.close()


def _gmail_ingest_sync_with_flag():
    """
    Gmail Ingest 작업 + 플래그 해제 (fire-and-forget용)
    """
    global _job_running
    try:
        _gmail_ingest_sync()
    finally:
        _job_running = False
        logger.info("Gmail Ingest Job 완료 (플래그 해제)")


def _gmail_ingest_sync():
    """
    Gmail Ingest 실제 작업 (별도 스레드에서 실행)
    
    - Gmail에서 새 메일 가져오기
    - incoming_messages 저장
    - conversation 생성/업데이트
    - 새 conversation에 대해 Draft 생성
    - ✅ Orchestrator 판단 및 AUTO_SEND 처리
    """
    # 이 스레드 전용 event loop 생성
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_gmail_ingest_async())
    finally:
        loop.close()


async def _gmail_ingest_async():
    """Gmail Ingest 비동기 작업 (실제 로직)"""
    from app.db.session import SessionLocal
    from app.adapters.gmail_airbnb import fetch_and_parse_recent_airbnb_messages
    from app.services.email_ingestion_service import ingest_airbnb_parsed_messages
    from app.services.auto_reply_service import AutoReplyService
    from app.services.conversation_thread_service import DraftService, SafetyGuardService, apply_safety_to_conversation
    from app.domain.models.conversation import Conversation, ConversationChannel, ConversationStatus, SafetyStatus
    from app.domain.models.incoming_message import IncomingMessage, MessageDirection
    from app.domain.intents import MessageActor
    from app.services.notification_service import NotificationService
    from sqlalchemy import select, asc
    
    start_time = datetime.utcnow()
    logger.info("=" * 60)
    logger.info(f"Gmail Ingest Job 실행 중 (Thread: {__import__('threading').current_thread().name})")
    logger.info(f"  시작 시간: {start_time.isoformat()}")
    logger.info("=" * 60)
    
    db = SessionLocal()
    try:
        # 1) Gmail 파싱 (최근 3일, 최대 15개)
        logger.info("[Step 1/5] Gmail API에서 메일 가져오는 중...")
        parsed_messages = fetch_and_parse_recent_airbnb_messages(
            db=db,
            max_results=15,
            newer_than_days=3,
        )
        total_parsed = len(parsed_messages)
        logger.info(f"  → Gmail에서 {total_parsed}개 메시지 파싱됨")
        
        if total_parsed == 0:
            logger.info("  → 새 메시지 없음, Job 종료")
            logger.info("-" * 60)
            return
        
        # 2) DB 인제스트 (incoming_messages + conversations 생성)
        logger.info("[Step 2/5] DB에 메시지 저장 중...")
        await ingest_airbnb_parsed_messages(db=db, parsed_messages=parsed_messages)
        db.commit()
        logger.info("  → DB 저장 완료")
        
        # 3) airbnb_thread_id 목록 추출 (중복 제거)
        thread_ids = set()
        for parsed in parsed_messages:
            tid = getattr(parsed, "airbnb_thread_id", None)
            if tid:
                thread_ids.add(tid)
        
        logger.info(f"[Step 3/5] {len(thread_ids)}개 thread 처리 예정")
        
        # 4) 각 Conversation에 대해 Draft 생성
        logger.info("[Step 4/5] Draft 생성 중...")
        from app.adapters.llm_client import get_openai_client
        openai_client = get_openai_client()
        auto_reply_service = AutoReplyService(db=db, openai_client=openai_client)
        draft_service = DraftService(db)
        guard = SafetyGuardService(db)
        
        # ✅ Orchestrator 초기화
        try:
            from app.services.orchestrator_core import OrchestratorService
            orchestrator = OrchestratorService(db)
            orchestrator_available = True
            logger.info("  → Orchestrator 활성화됨")
        except Exception as e:
            logger.warning(f"  → Orchestrator 초기화 실패: {e}, AUTO_SEND 비활성화")
            orchestrator_available = False
        
        stats = {
            "draft_created": 0,
            "skipped_sent": 0,
            "skipped_draft_exists": 0,
            "skipped_no_guest": 0,
            "skipped_no_conv": 0,
            "llm_failed": 0,
            "auto_sent": 0,  # ✅ 자동 발송 카운트
        }
        
        for idx, airbnb_thread_id in enumerate(thread_ids, 1):
            short_tid = airbnb_thread_id[:30] + "..." if len(airbnb_thread_id) > 30 else airbnb_thread_id
            
            # Conversation 조회
            conv = db.execute(
                select(Conversation).where(
                    Conversation.channel == ConversationChannel.gmail,
                    Conversation.airbnb_thread_id == airbnb_thread_id,
                )
            ).scalar_one_or_none()
            
            if not conv:
                logger.debug(f"  [{idx}] {short_tid} → SKIP (no conversation)")
                stats["skipped_no_conv"] += 1
                continue
            
            # 이미 처리된 conversation은 스킵
            if conv.status == ConversationStatus.sent:
                logger.debug(f"  [{idx}] {short_tid} → SKIP (already sent)")
                stats["skipped_sent"] += 1
                continue
            
            # 마지막 GUEST 메시지 찾기 (Draft 스킵 판단보다 먼저 조회)
            msgs = db.execute(
                select(IncomingMessage)
                .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
                .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
            ).scalars().all()
            
            last_guest_msg = None
            for m in reversed(msgs):
                if m.direction == MessageDirection.incoming and m.sender_actor == MessageActor.GUEST:
                    last_guest_msg = m
                    break
            
            if not last_guest_msg:
                logger.debug(f"  [{idx}] {short_tid} → SKIP (no guest message)")
                stats["skipped_no_guest"] += 1
                continue
            
            # Draft 스킵 판단: 기존 Draft가 있고, 그 이후 새 게스트 메시지가 없으면 스킵
            existing_draft = draft_service.get_latest(conversation_id=conv.id)
            if existing_draft and existing_draft.content:
                # Draft 생성 시점 이후에 새 게스트 메시지가 왔는지 확인
                if last_guest_msg.received_at and existing_draft.created_at:
                    if last_guest_msg.received_at <= existing_draft.created_at:
                        logger.debug(f"  [{idx}] {short_tid} → SKIP (draft exists, no new guest message)")
                        stats["skipped_draft_exists"] += 1
                        continue
                    else:
                        logger.info(f"  [{idx}] {short_tid} → New guest message after draft, regenerating...")
                else:
                    # 시간 비교 불가능하면 기존처럼 스킵
                    logger.debug(f"  [{idx}] {short_tid} → SKIP (draft exists, time comparison not possible)")
                    stats["skipped_draft_exists"] += 1
                    continue
            
            # LLM으로 Draft 생성
            # property_code는 reservation_info에서 조회 (Single Source of Truth)
            from app.services.property_resolver import PropertyResolver
            resolved = PropertyResolver(db).resolve(airbnb_thread_id)
            
            try:
                suggestion = await auto_reply_service.suggest_reply_for_message(
                    message_id=last_guest_msg.id,
                    locale="ko",
                    property_code=resolved.property_code,  # reservation_info 기반
                )
                
                if suggestion and suggestion.reply_text:
                    content = suggestion.reply_text
                    outcome_label = suggestion.outcome_label.to_dict() if suggestion.outcome_label else None
                    logger.info(f"  [{idx}] {short_tid} → ✓ Draft 생성 (LLM)")
                else:
                    content = draft_service.generate_draft(airbnb_thread_id=airbnb_thread_id)
                    outcome_label = None
                    logger.info(f"  [{idx}] {short_tid} → ✓ Draft 생성 (Template)")
            except Exception as e:
                logger.warning(f"  [{idx}] {short_tid} → LLM 실패: {str(e)[:50]}")
                content = draft_service.generate_draft(airbnb_thread_id=airbnb_thread_id)
                outcome_label = None
                stats["llm_failed"] += 1
            
            # Safety 평가
            safety, _ = guard.evaluate_text(text=content)
            
            # Draft 저장 (게스트 메시지 스냅샷 포함)
            # suggestion.guest_message: 병합된 연속 메시지 (LLM에 실제 들어간 입력)
            # fallback: 마지막 게스트 메시지
            guest_message_snapshot = (
                suggestion.guest_message
                if suggestion and suggestion.guest_message
                else (last_guest_msg.pure_guest_message if last_guest_msg else None)
            )
            draft = draft_service.upsert_latest(
                conversation=conv,
                content=content,
                safety=safety,
                outcome_label=outcome_label,
                guest_message_snapshot=guest_message_snapshot,
            )
            
            # Conversation 상태 업데이트
            apply_safety_to_conversation(conv, safety)
            db.add(conv)
            
            # ✅ Safety Block 시 알림 생성
            if safety == SafetyStatus.block:
                try:
                    notification_svc = NotificationService(db)
                    guest_name = last_guest_msg.guest_name if last_guest_msg else "게스트"
                    message_preview = (last_guest_msg.pure_guest_message or "")[:150] if last_guest_msg else ""
                    notification_svc.create_safety_alert(
                        property_code=resolved.property_code or "",  # reservation_info 기반
                        guest_name=guest_name or "게스트",
                        message_preview=message_preview,
                        airbnb_thread_id=conv.airbnb_thread_id,
                    )
                except Exception as e:
                    logger.warning("Failed to create safety alert notification: %s", e)
            
            # ✅ 입금/결제 확인 필요 알림 생성 (Rule Correction에서 감지된 경우)
            if outcome_label and outcome_label.get("rule_applied"):
                rules = outcome_label.get("rule_applied", [])
                has_payment_keyword = any("payment_keyword" in rule for rule in rules)
                
                if has_payment_keyword:
                    try:
                        notification_svc = NotificationService(db)
                        guest_name = last_guest_msg.guest_name if last_guest_msg else "게스트"
                        message_preview = (last_guest_msg.pure_guest_message or "")[:150] if last_guest_msg else ""
                        notification_svc.create_payment_verification_alert(
                            property_code=resolved.property_code or "",
                            guest_name=guest_name or "게스트",
                            message_preview=message_preview,
                            airbnb_thread_id=conv.airbnb_thread_id,
                        )
                        logger.info(f"  [{idx}] {short_tid} → 💰 입금 확인 알림 생성")
                    except Exception as e:
                        logger.warning("Failed to create payment verification alert: %s", e)
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # ✅ Orchestrator 판단 및 AUTO_SEND
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if orchestrator_available and draft and safety != SafetyStatus.block:
                try:
                    from app.services.orchestrator_core import EvidencePackage, Decision
                    from app.repositories.commitment_repository import CommitmentRepository
                    
                    commitment_repo = CommitmentRepository(db)
                    active_commitments = commitment_repo.get_active_by_thread_id(conv.airbnb_thread_id)
                    
                    # Evidence 구성
                    evidence = EvidencePackage(
                        draft_reply_id=draft.id,
                        conversation_id=conv.id,
                        property_code=resolved.property_code,  # reservation_info 기반
                        draft_content=content,
                        guest_message=last_guest_msg.pure_guest_message,
                        outcome_label=outcome_label,
                        active_commitments=[c.to_dict() for c in active_commitments],
                    )
                    
                    # 판단
                    decision_result = await orchestrator.evaluate_draft(evidence)
                    
                    logger.info(
                        f"  [{idx}] {short_tid} → Orchestrator: {decision_result.decision.value} "
                        f"(confidence={decision_result.confidence:.2f})"
                    )
                    
                    # AUTO_SEND 처리
                    if decision_result.decision == Decision.AUTO_SEND:
                        auto_send_result = await _attempt_auto_send(
                            db=db,
                            conv=conv,
                            draft=draft,
                            content=content,
                            orchestrator=orchestrator,
                            decision_result=decision_result,
                        )
                        if auto_send_result:
                            stats["auto_sent"] += 1
                            logger.info(f"  [{idx}] {short_tid} → 🚀 AUTO_SEND 완료!")
                        else:
                            logger.info(f"  [{idx}] {short_tid} → AUTO_SEND 실패, 수동 대기")
                            
                except Exception as e:
                    logger.warning(f"  [{idx}] {short_tid} → Orchestrator 오류: {e}")
            
            # ✅ Complaint 추출 (SENSITIVE/HIGH_RISK일 때만)
            if suggestion and suggestion.outcome_label:
                from app.services.auto_reply_service import SafetyOutcome
                safety_outcome = suggestion.outcome_label.safety_outcome
                
                logger.info(
                    f"  [{idx}] {short_tid} → safety_outcome={safety_outcome}, "
                    f"type={type(safety_outcome)}, checking SENSITIVE/HIGH_RISK..."
                )
                
                if safety_outcome in [SafetyOutcome.SENSITIVE, SafetyOutcome.HIGH_RISK]:
                    logger.info(f"  [{idx}] {short_tid} → Complaint 추출 시작...")
                    try:
                        from app.services.complaint_extractor import ComplaintExtractor
                        complaint_extractor = ComplaintExtractor(db, openai_client=openai_client)
                        complaint_result = complaint_extractor.extract_from_message(
                            message=last_guest_msg,
                            conversation=conv,
                        )
                        logger.info(
                            f"  [{idx}] {short_tid} → Complaint 추출 결과: "
                            f"has_complaint={complaint_result.has_complaint}, "
                            f"count={len(complaint_result.complaints)}"
                        )
                        if complaint_result.has_complaint:
                            stats["complaints_created"] = stats.get("complaints_created", 0) + len(complaint_result.complaints)
                            logger.info(
                                f"  [{idx}] {short_tid} → Complaint 생성: {len(complaint_result.complaints)}건"
                            )
                    except Exception as e:
                        logger.error(f"Failed to extract complaints: {e}", exc_info=True)
                else:
                    logger.info(f"  [{idx}] {short_tid} → safety_outcome이 SENSITIVE/HIGH_RISK 아님, 스킵")
            else:
                logger.info(f"  [{idx}] {short_tid} → suggestion 또는 outcome_label 없음, 스킵")
            
            stats["draft_created"] += 1
            
            # 🆕 각 conversation 처리 후 중간 commit (DB 연결 점유 시간 최소화)
            try:
                db.commit()
            except Exception as e:
                logger.warning(f"  [{idx}] {short_tid} → 중간 commit 실패: {e}")
                db.rollback()
        
        # 최종 commit (이미 중간에 했지만 safety net)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 미응답 경고 알림 생성 (30분 이상)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        try:
            from datetime import timedelta, timezone
            now_utc = datetime.now(timezone.utc)
            cutoff = now_utc - timedelta(minutes=30)
            
            # 30분 이상 미응답인 대화 찾기 (pending 상태)
            unanswered_convs = db.execute(
                select(Conversation)
                .where(Conversation.status == ConversationStatus.pending)
                .where(Conversation.updated_at < cutoff)
            ).scalars().all()
            
            unanswered_count = 0
            for conv in unanswered_convs:
                # 마지막 게스트 메시지 찾기
                last_guest = db.execute(
                    select(IncomingMessage)
                    .where(IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id)
                    .where(IncomingMessage.direction == MessageDirection.incoming)
                    .where(IncomingMessage.sender_actor == MessageActor.GUEST)
                    .order_by(IncomingMessage.received_at.desc())
                ).scalars().first()
                
                if last_guest and last_guest.received_at < cutoff:
                    minutes_unanswered = int((now_utc - last_guest.received_at).total_seconds() / 60)
                    notification_svc = NotificationService(db)
                    # property_code는 reservation_info에서 조회
                    from app.services.property_resolver import get_effective_property_code
                    effective_prop = get_effective_property_code(db, conv.airbnb_thread_id)
                    result = notification_svc.create_unanswered_warning(
                        property_code=effective_prop or "",
                        guest_name=last_guest.guest_name or "게스트",
                        minutes_unanswered=minutes_unanswered,
                        airbnb_thread_id=conv.airbnb_thread_id,
                    )
                    if result:
                        unanswered_count += 1
            
            if unanswered_count > 0:
                logger.info(f"  미응답 경고 알림 생성: {unanswered_count}건")
        except Exception as e:
            logger.warning(f"Failed to check unanswered conversations: {e}")
        
        # 완료 로그
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("-" * 60)
        logger.info("Gmail Ingest Job 완료")
        logger.info(f"  소요 시간: {duration:.1f}초")
        logger.info(f"  파싱된 메일: {total_parsed}개")
        logger.info(f"  Draft 생성: {stats['draft_created']}개")
        logger.info(f"  🚀 자동 발송: {stats['auto_sent']}개")  # ✅ 추가
        logger.info(f"  스킵 (이미 발송): {stats['skipped_sent']}개")
        logger.info(f"  스킵 (Draft 존재): {stats['skipped_draft_exists']}개")
        logger.info(f"  스킵 (게스트 메시지 없음): {stats['skipped_no_guest']}개")
        logger.info(f"  LLM 실패 (Template 사용): {stats['llm_failed']}개")
        logger.info("=" * 60)
        
        # ✅ WebSocket 브로드캐스트: 프론트엔드에 새로고침 알림
        try:
            from app.services.ws_manager import ws_manager
            # 변경사항이 있을 때만 브로드캐스트
            if stats['draft_created'] > 0 or stats['auto_sent'] > 0:
                sent_count = await ws_manager.broadcast_refresh(
                    scope="conversations",
                    reason="scheduler"
                )
                logger.info(f"  📡 WebSocket 브로드캐스트 완료 ({sent_count}개 클라이언트)")
        except Exception as e:
            logger.warning(f"WebSocket 브로드캐스트 실패 (무시됨): {e}")
        
    except Exception as e:
        logger.error(f"Gmail Ingest Job 실패: {e}")
        logger.exception("상세 에러:")
        db.rollback()
    finally:
        db.close()


async def _attempt_auto_send(
    db,
    conv,
    draft,
    content: str,
    orchestrator,
    decision_result,
) -> bool:
    """
    AUTO_SEND 시 실제 발송 시도
    
    Returns:
        bool: 발송 성공 여부
    """
    from sqlalchemy import select, desc
    from app.adapters.gmail_send_adapter import GmailSendAdapter
    from app.services.gmail_fetch_service import get_gmail_service
    from app.services.send_event_handler import SendEventHandler
    from app.domain.models.conversation import ConversationStatus, SendAction, SendActionLog
    from app.domain.models.incoming_message import IncomingMessage
    from app.services.orchestrator_core import HumanAction
    from app.services.property_resolver import get_effective_property_code
    
    # property_code는 reservation_info에서 조회 (Single Source of Truth)
    effective_property_code = get_effective_property_code(db, conv.airbnb_thread_id) or ""
    
    try:
        # Gmail 서비스 확인
        gmail_service = get_gmail_service(db)
        if not gmail_service:
            logger.warning("AUTO_SEND 실패: Gmail 서비스 없음")
            return False
        
        send_adapter = GmailSendAdapter(service=gmail_service)
        
        # ═══════════════════════════════════════════════════════════════
        # incoming_messages에서 reply_to, gmail_thread_id, subject 조회
        # (conversations 테이블에는 이 컬럼들이 없음)
        # ═══════════════════════════════════════════════════════════════
        last_incoming_msg = db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == conv.airbnb_thread_id)
            .where(IncomingMessage.direction == "incoming")
            .order_by(desc(IncomingMessage.received_at))
            .limit(1)
        ).scalar_one_or_none()
        
        if not last_incoming_msg:
            logger.warning(f"AUTO_SEND 실패: incoming_message 없음 (thread={conv.airbnb_thread_id[:30]}...)")
            return False
        
        reply_to = last_incoming_msg.reply_to
        gmail_thread_id = last_incoming_msg.gmail_thread_id
        email_subject = last_incoming_msg.subject
        
        # Reply-To 확인
        if not reply_to:
            logger.warning(f"AUTO_SEND 실패: Reply-To 없음 (thread={conv.airbnb_thread_id[:30]}...)")
            return False
        
        # Gmail thread ID 확인
        if not gmail_thread_id:
            logger.warning(f"AUTO_SEND 실패: Gmail thread ID 없음 (thread={conv.airbnb_thread_id[:30]}...)")
            return False
        
        # 발송
        resp = send_adapter.send_reply(
            gmail_thread_id=gmail_thread_id,
            to_email=reply_to,
            subject=f"Re: {email_subject or 'Airbnb Inquiry'}",
            reply_text=content,
            original_message_id=None,
        )
        
        if resp and resp.get("id"):
            out_gmail_message_id = resp.get("id")
            out_gmail_thread_id = resp.get("threadId")
            
            # Conversation 상태 업데이트
            conv.status = ConversationStatus.sent
            
            # ✅ SendActionLog 생성 (auto_sent 기록)
            send_log = SendActionLog(
                conversation_id=conv.id,
                airbnb_thread_id=conv.airbnb_thread_id,
                property_code=effective_property_code,  # reservation_info 기반
                actor="system",
                action=SendAction.auto_sent,
                content_sent=content,
                payload_json={
                    "auto_send": True,
                    "gmail_thread_id": gmail_thread_id,
                    "gmail_message_id": out_gmail_message_id,
                },
            )
            db.add(send_log)
            
            # SendEventHandler로 후처리 (Commitment + Embedding)
            send_handler = SendEventHandler(db)
            
            # 게스트 메시지 가져오기 (DraftReply의 스냅샷 우선, 없으면 위에서 조회한 last_incoming_msg 사용)
            guest_message_for_embedding = draft.guest_message_snapshot or ""
            if not guest_message_for_embedding and last_incoming_msg:
                guest_message_for_embedding = last_incoming_msg.pure_guest_message or ""
            
            await send_handler.on_message_sent(
                sent_text=content,
                airbnb_thread_id=conv.airbnb_thread_id,
                property_code=effective_property_code,  # reservation_info 기반
                conversation_id=conv.id,
                # Few-shot Learning용
                guest_message=guest_message_for_embedding,
                was_edited=draft.is_edited,
            )
            
            # Orchestrator 로그 업데이트
            if decision_result.decision_log_id:
                orchestrator.record_human_action(
                    decision_log_id=decision_result.decision_log_id,
                    action=HumanAction.AUTO_SENT,
                    actor="system",
                )
                orchestrator.record_sent(
                    decision_log_id=decision_result.decision_log_id,
                    final_content=content,
                )
            
            logger.info(f"AUTO_SEND 성공: {conv.airbnb_thread_id[:30]}...")
            return True
        else:
            logger.warning("AUTO_SEND 실패: Gmail 발송 실패")
            return False
            
    except Exception as e:
        logger.error(f"AUTO_SEND 오류: {e}")
        return False


def start_scheduler(interval_minutes: int = 2):
    """
    스케줄러 시작
    
    Args:
        interval_minutes: 실행 간격 (분), 기본 5분
    """
    global _scheduler
    
    if _scheduler is not None:
        logger.warning("스케줄러가 이미 실행 중입니다")
        return
    
    _scheduler = AsyncIOScheduler()
    
    # Gmail Ingest Job 등록 (2분 간격)
    _scheduler.add_job(
        gmail_ingest_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="gmail_ingest_job",
        name="Gmail Ingest + Draft 생성 + Orchestrator",
        replace_existing=True,
    )
    
    # iCal Sync Job 등록 (30분 간격)
    _scheduler.add_job(
        ical_sync_job,
        trigger=IntervalTrigger(minutes=30),
        id="ical_sync_job",
        name="iCal 동기화",
        replace_existing=True,
    )
    
    # Daily Reminder Job 등록 (매일 오전 9시, KST 기준)
    _scheduler.add_job(
        daily_reminder_job,
        trigger=CronTrigger(hour=0, minute=0, timezone="Asia/Seoul"),  # KST 09:00 = UTC 00:00
        id="daily_reminder_job",
        name="일일 리마인더 (OC)",
        replace_existing=True,
    )
    
    # Property FAQ Stats Job 등록 (매일 새벽 2시, KST 기준)
    _scheduler.add_job(
        property_faq_stats_job,
        trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Seoul"),  # KST 02:00
        id="property_faq_stats_job",
        name="Property FAQ 통계 집계",
        replace_existing=True,
    )
    
    _scheduler.start()
    
    logger.info("=" * 60)
    logger.info("TONO Scheduler 시작됨 (Orchestrator 연동)")
    logger.info(f"  Gmail Ingest: {interval_minutes}분 간격")
    logger.info(f"  iCal Sync: 30분 간격")
    logger.info(f"  Daily Reminder: 매일 09:00 KST")
    logger.info(f"  FAQ Stats: 매일 02:00 KST")
    logger.info(f"  다음 Gmail 실행: {_scheduler.get_job('gmail_ingest_job').next_run_time}")
    logger.info(f"  다음 iCal 실행: {_scheduler.get_job('ical_sync_job').next_run_time}")
    logger.info(f"  다음 Daily 실행: {_scheduler.get_job('daily_reminder_job').next_run_time}")
    logger.info(f"  다음 FAQ Stats 실행: {_scheduler.get_job('property_faq_stats_job').next_run_time}")
    logger.info("=" * 60)


def shutdown_scheduler():
    """스케줄러 및 ThreadPool 종료"""
    global _scheduler, _executor
    
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("TONO Scheduler 종료됨")
    
    if _executor is not None:
        _executor.shutdown(wait=True)
        logger.info("TONO Scheduler ThreadPool 종료됨")


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """현재 스케줄러 인스턴스 반환"""
    return _scheduler


def is_job_running() -> bool:
    """현재 Job이 실행 중인지 확인"""
    return _job_running


async def run_job_now():
    """
    수동으로 Job 즉시 실행 (테스트용)
    """
    logger.info("Job 수동 실행 요청됨")
    await gmail_ingest_job()


async def run_faq_stats_job_now():
    """
    Property FAQ Stats Job 수동 실행 (테스트용)
    """
    logger.info("Property FAQ Stats Job 수동 실행 요청됨")
    await property_faq_stats_job()
