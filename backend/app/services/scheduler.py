# backend/app/services/scheduler.py
"""
TONO Scheduler Service (APScheduler 기반)

5분마다 Gmail Ingest + Draft 생성을 실행합니다.

사용법:
    from app.services.scheduler import start_scheduler, shutdown_scheduler
    
    # FastAPI lifespan에서
    start_scheduler()
    ...
    shutdown_scheduler()
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

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


async def gmail_ingest_job():
    """
    Gmail Ingest Job
    
    - Gmail에서 새 메일 가져오기
    - incoming_messages 저장
    - conversation 생성/업데이트
    - 새 conversation에 대해 Draft 생성
    """
    from app.db.session import SessionLocal
    from app.adapters.gmail_airbnb import fetch_and_parse_recent_airbnb_messages
    from app.services.email_ingestion_service import ingest_airbnb_parsed_messages
    from app.services.auto_reply_service import AutoReplyService
    from app.services.conversation_thread_service import DraftService, SafetyGuardService, apply_safety_to_conversation
    from app.domain.models.conversation import Conversation, ConversationChannel, ConversationStatus
    from app.domain.models.incoming_message import IncomingMessage, MessageDirection
    from app.domain.intents import MessageActor
    from sqlalchemy import select, asc
    
    start_time = datetime.utcnow()
    logger.info("=" * 60)
    logger.info(f"Gmail Ingest Job 시작")
    logger.info(f"  시작 시간: {start_time.isoformat()}")
    logger.info("=" * 60)
    
    db = SessionLocal()
    try:
        # 1) Gmail 파싱 (최근 3일, 최대 50개)
        logger.info("[Step 1/4] Gmail API에서 메일 가져오는 중...")
        parsed_messages = fetch_and_parse_recent_airbnb_messages(
            db=db,
            max_results=50,
            newer_than_days=3,
        )
        total_parsed = len(parsed_messages)
        logger.info(f"  → Gmail에서 {total_parsed}개 메시지 파싱됨")
        
        if total_parsed == 0:
            logger.info("  → 새 메시지 없음, Job 종료")
            logger.info("-" * 60)
            return
        
        # 2) DB 인제스트 (incoming_messages + conversations 생성)
        logger.info("[Step 2/4] DB에 메시지 저장 중...")
        await ingest_airbnb_parsed_messages(db=db, parsed_messages=parsed_messages)
        db.commit()
        logger.info("  → DB 저장 완료")
        
        # 3) airbnb_thread_id 목록 추출 (중복 제거)
        thread_ids = set()
        for parsed in parsed_messages:
            tid = getattr(parsed, "airbnb_thread_id", None)
            if tid:
                thread_ids.add(tid)
        
        logger.info(f"[Step 3/4] {len(thread_ids)}개 thread 처리 예정")
        
        # 4) 각 Conversation에 대해 Draft 생성
        logger.info("[Step 4/4] Draft 생성 중...")
        auto_reply_service = AutoReplyService(db=db)
        draft_service = DraftService(db)
        guard = SafetyGuardService(db)
        
        stats = {
            "draft_created": 0,
            "skipped_sent": 0,
            "skipped_draft_exists": 0,
            "skipped_no_guest": 0,
            "skipped_no_conv": 0,
            "llm_failed": 0,
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
            
            # 이미 draft가 있는 경우 스킵
            existing_draft = draft_service.get_latest(conversation_id=conv.id)
            if existing_draft and existing_draft.content:
                logger.debug(f"  [{idx}] {short_tid} → SKIP (draft exists)")
                stats["skipped_draft_exists"] += 1
                continue
            
            # 마지막 GUEST 메시지 찾기
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
            
            # LLM으로 Draft 생성
            try:
                suggestion = await auto_reply_service.suggest_reply_for_message(
                    message_id=last_guest_msg.id,
                    locale="ko",
                    property_code=last_guest_msg.property_code,
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
            
            # Draft 저장
            draft_service.upsert_latest(
                conversation=conv,
                content=content,
                safety=safety,
                outcome_label=outcome_label,
            )
            
            # Conversation 상태 업데이트
            apply_safety_to_conversation(conv, safety)
            db.add(conv)
            
            stats["draft_created"] += 1
        
        db.commit()
        
        # 완료 로그
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("-" * 60)
        logger.info("Gmail Ingest Job 완료")
        logger.info(f"  소요 시간: {duration:.1f}초")
        logger.info(f"  파싱된 메일: {total_parsed}개")
        logger.info(f"  Draft 생성: {stats['draft_created']}개")
        logger.info(f"  스킵 (이미 발송): {stats['skipped_sent']}개")
        logger.info(f"  스킵 (Draft 존재): {stats['skipped_draft_exists']}개")
        logger.info(f"  스킵 (게스트 메시지 없음): {stats['skipped_no_guest']}개")
        logger.info(f"  LLM 실패 (Template 사용): {stats['llm_failed']}개")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Gmail Ingest Job 실패: {e}")
        logger.exception("상세 에러:")
        db.rollback()
    finally:
        db.close()


async def expire_pending_reservations_job():
    """
    예약 요청 만료 처리 Job
    
    24시간이 지난 pending 상태의 예약 요청을 expired로 변경.
    매 시간마다 실행.
    """
    from app.db.session import SessionLocal
    
    logger.info("-" * 40)
    logger.info("예약 요청 만료 처리 Job 시작")
    
    db = SessionLocal()
    try:
        from app.repositories.pending_reservation_request_repository import (
            PendingReservationRequestRepository,
        )
        repo = PendingReservationRequestRepository(db)
        expired_count = repo.expire_old_requests()
        
        if expired_count > 0:
            logger.info(f"  → {expired_count}개 예약 요청 만료 처리됨")
        else:
            logger.info("  → 만료 처리할 요청 없음")
        
    except ImportError:
        logger.info("  → pending_reservation_request 모듈 없음 - 스킵")
    except Exception as e:
        logger.error(f"예약 요청 만료 처리 Job 실패: {e}")
        db.rollback()
    finally:
        db.close()
    
    logger.info("-" * 40)


def start_scheduler(interval_minutes: int = 5):
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
    
    # Gmail Ingest Job 등록
    _scheduler.add_job(
        gmail_ingest_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="gmail_ingest_job",
        name="Gmail Ingest + Draft 생성",
        replace_existing=True,
    )
    
    # 예약 요청 만료 처리 Job 등록 (1시간마다)
    _scheduler.add_job(
        expire_pending_reservations_job,
        trigger=IntervalTrigger(hours=1),
        id="expire_pending_reservations_job",
        name="예약 요청 만료 처리",
        replace_existing=True,
    )
    
    _scheduler.start()
    
    logger.info("=" * 60)
    logger.info("TONO Scheduler 시작됨")
    logger.info(f"  [Job 1] Gmail Ingest: {interval_minutes}분 간격")
    logger.info(f"          다음 실행: {_scheduler.get_job('gmail_ingest_job').next_run_time}")
    logger.info(f"  [Job 2] 예약 요청 만료 처리: 1시간 간격")
    logger.info(f"          다음 실행: {_scheduler.get_job('expire_pending_reservations_job').next_run_time}")
    logger.info("=" * 60)


def shutdown_scheduler():
    """스케줄러 종료"""
    global _scheduler
    
    if _scheduler is None:
        return
    
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("TONO Scheduler 종료됨")


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """현재 스케줄러 인스턴스 반환"""
    return _scheduler


async def run_job_now():
    """
    수동으로 Job 즉시 실행 (테스트용)
    """
    logger.info("Job 수동 실행 요청됨")
    await gmail_ingest_job()
