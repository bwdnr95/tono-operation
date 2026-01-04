# backend/app/scripts/backfill_embeddings.py
"""
draft_replies 기반으로 answer_embeddings 테이블 백필 (품질 필터링 적용)

기존 migrate_embeddings.py와 차이점:
1. 품질 필터링: 20자 미만, 불량 패턴 제외
2. 중복 방지: 이미 answer_embeddings에 있는 conversation_id 스킵
3. sent 상태인 conversation만 대상

사용법:
    python -m app.scripts.backfill_embeddings
    
    # 드라이런 (실제 저장 없이 대상만 확인)
    python -m app.scripts.backfill_embeddings --dry-run
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select, exists, and_

from app.db.session import SessionLocal
from app.domain.models.conversation import Conversation, ConversationStatus, DraftReply
from app.domain.models.answer_embedding import AnswerEmbedding
from app.services.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# 불량 패턴 리스트
BAD_PATTERNS = [
    "%반응%했습니다%",
    "%이미지가 전송됨%",
    "%공동 호스트%",
    "%귤이%",
]

MIN_MESSAGE_LENGTH = 20


def is_valid_guest_message(message: str) -> bool:
    """게스트 메시지 품질 검증"""
    if not message:
        return False
    
    message = message.strip()
    
    # 길이 체크
    if len(message) < MIN_MESSAGE_LENGTH:
        return False
    
    # 불량 패턴 체크
    message_lower = message.lower()
    for pattern in BAD_PATTERNS:
        # SQL LIKE 패턴을 Python으로 변환
        check_pattern = pattern.replace("%", "").lower()
        if check_pattern in message_lower:
            return False
    
    return True


def backfill_embeddings(dry_run: bool = False):
    """
    draft_replies 기반으로 answer_embeddings 백필
    
    Args:
        dry_run: True면 실제 저장 없이 대상만 확인
    """
    
    db = SessionLocal()
    embedding_service = EmbeddingService(db) if not dry_run else None
    
    try:
        # 백필 대상 조회: sent 상태 + guest_message_snapshot 있음 + 아직 임베딩 없음
        subquery = select(AnswerEmbedding.conversation_id)
        
        drafts_query = (
            select(DraftReply)
            .join(Conversation, DraftReply.conversation_id == Conversation.id)
            .where(
                and_(
                    Conversation.status == ConversationStatus.sent,
                    DraftReply.guest_message_snapshot.isnot(None),
                    DraftReply.guest_message_snapshot != "",
                    # 이미 임베딩 있는 건 제외
                    ~DraftReply.conversation_id.in_(subquery),
                )
            )
        )
        
        drafts = db.execute(drafts_query).scalars().all()
        
        logger.info(f"백필 후보 Draft {len(drafts)}건 발견")
        
        stats = {
            "total_candidates": len(drafts),
            "processed": 0,
            "skipped_quality": 0,
            "skipped_empty_answer": 0,
            "errors": 0,
        }
        
        valid_drafts = []
        
        for draft in drafts:
            try:
                conv = draft.conversation
                if not conv:
                    continue
                
                guest_message = draft.guest_message_snapshot
                
                # 품질 검증
                if not is_valid_guest_message(guest_message):
                    stats["skipped_quality"] += 1
                    logger.debug(f"품질 미달 스킵: {guest_message[:50]}...")
                    continue
                
                final_answer = draft.content
                if not final_answer or len(final_answer.strip()) < 5:
                    stats["skipped_empty_answer"] += 1
                    continue
                
                # 수정 여부 확인
                was_edited = draft.is_edited or (
                    draft.original_content and draft.original_content != draft.content
                )
                
                valid_drafts.append({
                    "guest_message": guest_message,
                    "final_answer": final_answer,
                    "property_code": conv.property_code,
                    "was_edited": was_edited,
                    "conversation_id": conv.id,
                    "airbnb_thread_id": conv.airbnb_thread_id,
                })
                
            except Exception as e:
                logger.error(f"Draft {draft.id} 처리 실패: {e}")
                stats["errors"] += 1
                continue
        
        logger.info(f"품질 검증 통과: {len(valid_drafts)}건")
        
        if dry_run:
            logger.info("=== DRY RUN 모드 ===")
            logger.info("실제 저장 없이 대상만 확인합니다.")
            for i, d in enumerate(valid_drafts[:10]):  # 샘플 10개만 출력
                logger.info(f"\n[{i+1}] property: {d['property_code']}, edited: {d['was_edited']}")
                logger.info(f"    Guest: {d['guest_message'][:80]}...")
                logger.info(f"    Answer: {d['final_answer'][:80]}...")
        else:
            # 실제 저장
            for i, d in enumerate(valid_drafts):
                try:
                    embedding_service.store_answer(
                        guest_message=d["guest_message"],
                        final_answer=d["final_answer"],
                        property_code=d["property_code"],
                        was_edited=d["was_edited"],
                        conversation_id=d["conversation_id"],
                        airbnb_thread_id=d["airbnb_thread_id"],
                    )
                    stats["processed"] += 1
                    
                    if stats["processed"] % 10 == 0:
                        logger.info(f"진행 중... {stats['processed']}건 처리")
                        db.commit()
                        
                except Exception as e:
                    logger.error(f"임베딩 저장 실패: {e}")
                    stats["errors"] += 1
                    continue
            
            db.commit()
        
        # 결과 출력
        logger.info("=" * 60)
        logger.info("백필 완료!")
        logger.info(f"  전체 후보: {stats['total_candidates']}건")
        logger.info(f"  품질 미달 스킵: {stats['skipped_quality']}건")
        logger.info(f"  빈 답변 스킵: {stats['skipped_empty_answer']}건")
        if not dry_run:
            logger.info(f"  처리됨: {stats['processed']}건")
        logger.info(f"  에러: {stats['errors']}건")
        logger.info("=" * 60)
        
        return stats
        
    except Exception as e:
        logger.error(f"백필 실패: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        logger.info("=== 임베딩 백필 시작 (DRY RUN) ===")
    else:
        logger.info("=== 임베딩 백필 시작 ===")
    
    backfill_embeddings(dry_run=dry_run)
    
    logger.info("=== 백필 완료 ===")
