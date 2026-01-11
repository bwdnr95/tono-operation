"""
Backfill Conversations Script

reservation_info 또는 incoming_messages가 있지만 conversation이 없는 케이스를 찾아
conversation을 생성합니다.

사용법:
    # Dry-run (실제 생성 없이 대상만 확인)
    python -m app.scripts.backfill_conversations --dry-run
    
    # 실제 실행
    python -m app.scripts.backfill_conversations
    
    # 특정 thread_id만 처리
    python -m app.scripts.backfill_conversations --thread-id 2404813919
"""
import argparse
import logging
from datetime import datetime

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.models.conversation import Conversation, ConversationChannel, ConversationStatus
from app.domain.models.reservation_info import ReservationInfo
from app.domain.models.incoming_message import IncomingMessage
from app.repositories.ota_listing_mapping_repository import OtaListingMappingRepository

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_missing_conversations(db: Session) -> list[dict]:
    """
    incoming_messages는 있지만 conversation이 없는 케이스 찾기
    
    핵심: group_code가 있지만 property_code가 없어서 conversation 생성이 스킵된 케이스
    
    Returns:
        list of dict with keys:
        - airbnb_thread_id
        - property_code: str | None
        - group_code: str | None
        - last_message_id: int
        - received_at: datetime | None
        - ota_listing_id: str | None
    """
    from sqlalchemy import func
    
    results = []
    mapping_repo = OtaListingMappingRepository(db)
    
    # airbnb_thread_id별 최신 메시지 ID 서브쿼리
    latest_msg_subq = (
        select(
            IncomingMessage.airbnb_thread_id,
            func.max(IncomingMessage.id).label("max_id")
        )
        .where(IncomingMessage.airbnb_thread_id.isnot(None))
        .group_by(IncomingMessage.airbnb_thread_id)
        .subquery()
    )
    
    # incoming_messages는 있지만 conversation이 없는 케이스
    stmt = (
        select(IncomingMessage)
        .join(
            latest_msg_subq,
            and_(
                IncomingMessage.airbnb_thread_id == latest_msg_subq.c.airbnb_thread_id,
                IncomingMessage.id == latest_msg_subq.c.max_id
            )
        )
        .outerjoin(
            Conversation,
            IncomingMessage.airbnb_thread_id == Conversation.airbnb_thread_id
        )
        .where(Conversation.id.is_(None))
    )
    
    for msg in db.execute(stmt).scalars().all():
        property_code = msg.property_code
        group_code = None
        
        # OTA 매핑에서 property_code, group_code 조회
        if msg.ota and msg.ota_listing_id:
            prop_from_mapping, group_code = mapping_repo.get_property_and_group_codes(
                ota=msg.ota,
                listing_id=msg.ota_listing_id,
                active_only=True,
            )
            if not property_code:
                property_code = prop_from_mapping
        
        # reservation_info에서 group_code 조회 (OTA 매핑에 없는 경우)
        if not group_code:
            res_info = db.execute(
                select(ReservationInfo)
                .where(ReservationInfo.airbnb_thread_id == msg.airbnb_thread_id)
            ).scalar_one_or_none()
            if res_info:
                group_code = res_info.group_code
                if not property_code:
                    property_code = res_info.property_code
        
        # property_code 또는 group_code가 있어야 함
        if not property_code and not group_code:
            logger.debug(
                "Skipping: no property_code or group_code - "
                "airbnb_thread_id=%s, ota=%s, listing_id=%s",
                msg.airbnb_thread_id,
                msg.ota,
                msg.ota_listing_id,
            )
            continue
        
        results.append({
            "airbnb_thread_id": msg.airbnb_thread_id,
            "property_code": property_code,
            "group_code": group_code,
            "last_message_id": msg.id,
            "received_at": msg.received_at,
            "ota_listing_id": msg.ota_listing_id,
        })
    
    return results


def create_conversation(
    db: Session,
    *,
    airbnb_thread_id: str,
    property_code: str | None,
    last_message_id: int | None,
    received_at: datetime | None,
) -> Conversation:
    """Conversation 생성"""
    now = datetime.utcnow()
    conv = Conversation(
        channel=ConversationChannel.gmail,
        airbnb_thread_id=airbnb_thread_id,
        last_message_id=last_message_id,
        status=ConversationStatus.pending,
        property_code=property_code,
        received_at=received_at,
        last_message_at=received_at or now,
        is_read=False,
    )
    db.add(conv)
    db.flush()
    return conv


def backfill_conversations(
    db: Session,
    *,
    dry_run: bool = True,
    thread_id: str | None = None,
) -> dict:
    """
    누락된 conversation 백필
    
    Args:
        db: Database session
        dry_run: True면 실제 생성 없이 대상만 출력
        thread_id: 특정 thread_id만 처리
        
    Returns:
        {"found": int, "created": int, "skipped": int}
    """
    missing = find_missing_conversations(db)
    
    if thread_id:
        missing = [m for m in missing if m["airbnb_thread_id"] == thread_id]
    
    logger.info("Found %d missing conversations", len(missing))
    
    created = 0
    skipped = 0
    
    for item in missing:
        logger.info(
            "  airbnb_thread_id=%s, property_code=%s, group_code=%s, ota_listing_id=%s",
            item["airbnb_thread_id"],
            item["property_code"],
            item["group_code"],
            item.get("ota_listing_id"),
        )
        
        if dry_run:
            continue
        
        try:
            conv = create_conversation(
                db,
                airbnb_thread_id=item["airbnb_thread_id"],
                property_code=item["property_code"],
                last_message_id=item["last_message_id"],
                received_at=item["received_at"],
            )
            logger.info(
                "  → Created conversation: id=%s",
                conv.id,
            )
            created += 1
        except Exception as e:
            logger.error(
                "  → Failed to create conversation: %s",
                e,
            )
            skipped += 1
    
    if not dry_run:
        db.commit()
        logger.info("Committed %d new conversations", created)
    
    return {
        "found": len(missing),
        "created": created,
        "skipped": skipped,
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill missing conversations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating",
    )
    parser.add_argument(
        "--thread-id",
        type=str,
        help="Process only specific airbnb_thread_id",
    )
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        result = backfill_conversations(
            db,
            dry_run=args.dry_run,
            thread_id=args.thread_id,
        )
        
        print("\n" + "=" * 50)
        print(f"Found:   {result['found']}")
        print(f"Created: {result['created']}")
        print(f"Skipped: {result['skipped']}")
        
        if args.dry_run:
            print("\n(Dry-run mode - no changes made)")
            print("Run without --dry-run to create conversations")
    finally:
        db.close()


if __name__ == "__main__":
    main()
