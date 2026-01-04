# backend/app/scripts/migrate_embeddings.py
"""
기존 발송된 답변들을 임베딩하여 answer_embeddings 테이블에 저장

사용법:
    python -m app.scripts.migrate_embeddings
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.incoming_message import IncomingMessage, MessageDirection
from app.domain.intents import MessageActor
from app.services.embedding_service import EmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def migrate_sent_conversations():
    """guest_message_snapshot이 있는 DraftReply 기반으로 임베딩"""
    
    db = SessionLocal()
    embedding_service = EmbeddingService(db)
    
    try:
        # guest_message_snapshot이 있는 DraftReply만 조회
        from app.domain.models.conversation import DraftReply
        
        drafts = db.execute(
            select(DraftReply)
            .where(DraftReply.guest_message_snapshot.isnot(None))
            .where(DraftReply.guest_message_snapshot != "")
        ).scalars().all()
        
        logger.info(f"guest_message_snapshot이 있는 Draft {len(drafts)}건 발견")
        
        stats = {
            "processed": 0,
            "skipped_empty": 0,
            "skipped_no_conv": 0,
            "errors": 0,
        }
        
        for draft in drafts:
            try:
                conv = draft.conversation
                if not conv:
                    stats["skipped_no_conv"] += 1
                    continue
                
                guest_message = draft.guest_message_snapshot
                if not guest_message or len(guest_message.strip()) < 5:
                    stats["skipped_empty"] += 1
                    continue
                
                final_answer = draft.content
                if not final_answer or len(final_answer.strip()) < 5:
                    stats["skipped_empty"] += 1
                    continue
                
                # 수정 여부 확인
                was_edited = draft.is_edited or (
                    draft.original_content and draft.original_content != draft.content
                )
                
                # 임베딩 저장
                embedding_service.store_answer(
                    guest_message=guest_message,
                    final_answer=final_answer,
                    property_code=conv.property_code,
                    was_edited=was_edited,
                    conversation_id=conv.id,
                    airbnb_thread_id=conv.airbnb_thread_id,
                )
                
                stats["processed"] += 1
                
                if stats["processed"] % 10 == 0:
                    logger.info(f"진행 중... {stats['processed']}건 처리")
                    db.commit()
                    
            except Exception as e:
                logger.error(f"Draft {draft.id} 처리 실패: {e}")
                stats["errors"] += 1
                continue
        
        db.commit()
        
        logger.info("=" * 50)
        logger.info("마이그레이션 완료!")
        logger.info(f"  처리됨: {stats['processed']}건")
        logger.info(f"  스킵 (빈 메시지): {stats['skipped_empty']}건")
        logger.info(f"  스킵 (conversation 없음): {stats['skipped_no_conv']}건")
        logger.info(f"  에러: {stats['errors']}건")
        logger.info("=" * 50)
        
        return stats
        
    except Exception as e:
        logger.error(f"마이그레이션 실패: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("=== 임베딩 마이그레이션 시작 ===")
    migrate_sent_conversations()
    logger.info("=== 마이그레이션 완료 ===")
