# backend/app/services/email_ingestion_service.py
"""
Email Ingestion Service (v4 - Alteration Request 지원)

변경사항:
  - AirbnbIntentClassifier 제거
  - MessageIntentLabelService 제거
  - intent_result 관련 로직 제거
  - Alteration Request 처리 추가
  - Lazy matching (reservation_code → airbnb_thread_id)
  - Fallback reservation_info 생성 제거
"""
from __future__ import annotations

from typing import Iterable, Optional
import logging

from sqlalchemy.orm import Session

from app.domain.models.conversation import ConversationChannel
from app.domain.models.reservation_info import ReservationStatus
from app.services.conversation_thread_service import ConversationService

from app.domain.intents import (
    MessageActor,
    MessageActionability,
)
from app.services.airbnb_message_origin_classifier import (
    classify_airbnb_message_origin,
)
from app.services.airbnb_guest_message_extractor import (
    extract_guest_message_segment,
)

from app.repositories.messages import IncomingMessageRepository
from app.repositories.ota_listing_mapping_repository import OtaListingMappingRepository
from app.repositories.reservation_info_repository import (
    ReservationInfoRepository,
    _parse_time_string,
)
from app.repositories.alteration_request_repository import AlterationRequestRepository
from app.services.message_processor_service import process_message_after_ingestion

logger = logging.getLogger(__name__)


def _save_reservation_info(
    db: Session,
    parsed,
    gmail_message_id: str,
) -> None:
    """
    ParsedInternalMessage에서 예약 정보를 추출하여 reservation_info 테이블에 저장.
    
    시스템 메일(booking_confirmation)에서 호출됨.
    - reservation_code 기준으로 기존 레코드 조회
    - 있으면 UPDATE, 없으면 INSERT
    - airbnb_thread_id는 메일에서 파싱한 실제 값 사용 (없으면 fallback)
    - status는 confirmed (CSV 수기 입력과 구분)
    """
    repo = ReservationInfoRepository(db)
    reservation_code = getattr(parsed, "reservation_code", None)
    
    if not reservation_code:
        logger.warning(
            "Cannot save reservation_info: missing reservation_code gmail_message_id=%s",
            gmail_message_id,
        )
        return
    
    # reservation_code로 기존 레코드 조회
    existing = repo.get_by_reservation_code(reservation_code)
    
    if existing:
        # 기존 레코드 UPDATE (airbnb_thread_id는 유지)
        repo.update(
            existing,
            guest_name=getattr(parsed, "guest_name", None),
            guest_count=getattr(parsed, "guest_count", None),
            child_count=getattr(parsed, "child_count", None),
            infant_count=getattr(parsed, "infant_count", None),
            pet_count=getattr(parsed, "pet_count", None),
            checkin_date=getattr(parsed, "checkin_date", None),
            checkout_date=getattr(parsed, "checkout_date", None),
            checkin_time=_parse_time_string(getattr(parsed, "checkin_time", None)),
            checkout_time=_parse_time_string(getattr(parsed, "checkout_time", None)),
            property_code=getattr(parsed, "property_code", None),
            listing_id=getattr(parsed, "ota_listing_id", None),
            listing_name=getattr(parsed, "ota_listing_name", None),
            total_price=getattr(parsed, "total_price", None),
            host_payout=getattr(parsed, "host_payout", None),
            nights=getattr(parsed, "nights", None),
            source_template=getattr(parsed, "x_template", None),
            gmail_message_id=gmail_message_id,
        )
        logger.info(
            "Updated reservation_info: reservation_code=%s",
            reservation_code,
        )
    else:
        # 새 레코드 INSERT
        # 메일에서 파싱한 실제 airbnb_thread_id 사용 (없으면 fallback)
        airbnb_thread_id = getattr(parsed, "airbnb_thread_id", None)
        if not airbnb_thread_id:
            airbnb_thread_id = f"pending_{reservation_code.lower()}"
        
        repo.create(
            airbnb_thread_id=airbnb_thread_id,
            guest_name=getattr(parsed, "guest_name", None),
            guest_count=getattr(parsed, "guest_count", None),
            child_count=getattr(parsed, "child_count", None),
            infant_count=getattr(parsed, "infant_count", None),
            pet_count=getattr(parsed, "pet_count", None),
            reservation_code=reservation_code,
            checkin_date=getattr(parsed, "checkin_date", None),
            checkout_date=getattr(parsed, "checkout_date", None),
            checkin_time=_parse_time_string(getattr(parsed, "checkin_time", None)),
            checkout_time=_parse_time_string(getattr(parsed, "checkout_time", None)),
            property_code=getattr(parsed, "property_code", None),
            listing_id=getattr(parsed, "ota_listing_id", None),
            listing_name=getattr(parsed, "ota_listing_name", None),
            total_price=getattr(parsed, "total_price", None),
            host_payout=getattr(parsed, "host_payout", None),
            nights=getattr(parsed, "nights", None),
            source_template=getattr(parsed, "x_template", None),
            gmail_message_id=gmail_message_id,
        )
        logger.info(
            "Created reservation_info: reservation_code=%s, airbnb_thread_id=%s",
            reservation_code,
            airbnb_thread_id,
        )


def _handle_booking_inquiry(
    db: Session,
    parsed,
    gmail_message_id: str,
    repo,
    mapping_repo,
) -> None:
    """
    예약 문의(booking_inquiry) 처리.
    
    문의 단계에서는 reservation_info가 없으므로 lazy matching 불필요.
    - incoming_message 생성
    - conversation upsert
    - 후처리 (알림, draft 등)
    """
    from app.services.conversation_thread_service import ConversationService
    from app.domain.models.conversation import ConversationChannel
    from app.services.airbnb_origin_classifier import classify_airbnb_message_origin
    from app.services.airbnb_guest_message_extractor import extract_guest_message_segment
    
    # 중복 체크
    existing = repo.get_by_gmail_message_id(gmail_message_id)
    if existing is not None:
        logger.info(
            "Booking inquiry: skip already ingested gmail_message_id=%s (incoming_message_id=%s)",
            gmail_message_id,
            existing.id,
        )
        return

    airbnb_thread_id = getattr(parsed, "airbnb_thread_id", None)
    if not airbnb_thread_id:
        logger.warning(
            "Booking inquiry: skip without airbnb_thread_id gmail_message_id=%s",
            gmail_message_id,
        )
        return

    decoded_text_body = getattr(parsed, "decoded_text_body", None)
    decoded_html_body = getattr(parsed, "decoded_html_body", None)
    sender_role = getattr(parsed, "sender_role", None)

    origin = classify_airbnb_message_origin(
        decoded_text_body=decoded_text_body,
        decoded_html_body=decoded_html_body,
        subject=getattr(parsed, "subject", None),
        snippet=getattr(parsed, "snippet", None),
        sender_role=sender_role,
    )

    # pure_guest_message 추출
    if sender_role:
        pure_guest_message = decoded_text_body or ""
    else:
        pure_guest_message = extract_guest_message_segment(decoded_text_body or "")

    # property_code 매핑
    property_code = getattr(parsed, "property_code", None)
    ota = getattr(parsed, "ota", None)
    ota_listing_id = getattr(parsed, "ota_listing_id", None)
    if not property_code and ota and ota_listing_id:
        try:
            mapping = mapping_repo.get_by_ota_listing_id(
                ota=ota,
                listing_id=ota_listing_id,
                active_only=True,
            )
            if mapping is not None:
                property_code = mapping.property_code
        except Exception as exc:
            logger.warning(
                "Booking inquiry: failed to map property_code ota=%s listing_id=%s err=%s",
                ota,
                ota_listing_id,
                exc,
            )

    # incoming_message 생성
    msg = repo.create_from_parsed(
        gmail_message_id=gmail_message_id,
        airbnb_thread_id=airbnb_thread_id,
        subject=getattr(parsed, "subject", None),
        from_email=getattr(parsed, "from_email", None),
        reply_to=getattr(parsed, "reply_to", None),
        received_at=getattr(parsed, "received_at", None),
        origin=origin,
        intent_result=None,
        pure_guest_message=pure_guest_message,
        ota=ota,
        ota_listing_id=ota_listing_id,
        ota_listing_name=getattr(parsed, "ota_listing_name", None),
        property_code=property_code,
        guest_name=getattr(parsed, "guest_name", None),
        checkin_date=getattr(parsed, "checkin_date", None),
        checkout_date=getattr(parsed, "checkout_date", None),
    )

    # Conversation upsert
    conversation = None
    if not property_code:
        logger.warning(
            "Booking inquiry: skip conversation upsert (no property_code) gmail_message_id=%s",
            gmail_message_id,
        )
    else:
        inquiry_context = {
            "check_in": str(getattr(parsed, "checkin_date", None)) if getattr(parsed, "checkin_date", None) else None,
            "check_out": str(getattr(parsed, "checkout_date", None)) if getattr(parsed, "checkout_date", None) else None,
            "guest_count": getattr(parsed, "guest_count", None),
            "property_name": getattr(parsed, "ota_listing_name", None),
            "reply_via_email_disabled": True,  # 문의는 이메일 답장 불가
        }
        logger.info(
            "Booking inquiry (email reply disabled): airbnb_thread_id=%s, inquiry_context=%s",
            airbnb_thread_id,
            inquiry_context,
        )
        
        conversation = ConversationService(db).upsert_for_thread(
            channel=ConversationChannel.gmail,
            airbnb_thread_id=airbnb_thread_id,
            last_message_id=msg.id,
            property_code=property_code,
            received_at=msg.received_at,
        )

    # 후처리 (Staff Notification, Draft 생성 등)
    process_result = process_message_after_ingestion(
        db=db,
        message=msg,
        email_type="booking_inquiry",
        conversation=conversation,
    )
    if process_result.processed:
        logger.info(
            "Booking inquiry post-processing completed: message_id=%s, "
            "draft_created=%s, notification_created=%s",
            msg.id,
            process_result.draft_created,
            process_result.notification_created,
        )


def _update_existing_conversation_info(
    db: Session,
    parsed,
    airbnb_thread_id: str,
) -> bool:
    """
    예약 확정(BOOKING_CONFIRMATION) 시 기존 conversation/incoming_message 정보 업데이트.
    
    BOOKING_INITIAL_INQUIRY로 생성된 conversation이 있으면:
    - 게스트 이름, 체크인/체크아웃 날짜를 확정 정보로 업데이트
    
    Returns:
        업데이트 성공 여부
    """
    from sqlalchemy import select
    from app.domain.models.incoming_message import IncomingMessage, MessageDirection
    
    guest_name = getattr(parsed, "guest_name", None)
    checkin_date = getattr(parsed, "checkin_date", None)
    checkout_date = getattr(parsed, "checkout_date", None)
    property_code = getattr(parsed, "property_code", None)
    
    # 해당 thread의 기존 incoming 메시지들 조회
    existing_messages = db.execute(
        select(IncomingMessage)
        .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
        .where(IncomingMessage.direction == MessageDirection.incoming)
    ).scalars().all()
    
    if not existing_messages:
        return False
    
    updated = False
    for msg in existing_messages:
        needs_update = False
        
        # 게스트 이름 업데이트 (기존에 없거나 확정 정보가 있으면)
        if guest_name and (not msg.guest_name or msg.guest_name != guest_name):
            msg.guest_name = guest_name
            needs_update = True
        
        # 체크인 날짜 업데이트
        if checkin_date and (not msg.checkin_date or msg.checkin_date != checkin_date):
            msg.checkin_date = checkin_date
            needs_update = True
        
        # 체크아웃 날짜 업데이트
        if checkout_date and (not msg.checkout_date or msg.checkout_date != checkout_date):
            msg.checkout_date = checkout_date
            needs_update = True
        
        # property_code 업데이트
        if property_code and (not msg.property_code or msg.property_code != property_code):
            msg.property_code = property_code
            needs_update = True
        
        if needs_update:
            db.add(msg)
            updated = True
    
    if updated:
        db.flush()
        logger.info(
            "Updated existing conversation info from booking confirmation: "
            "airbnb_thread_id=%s, guest_name=%s, checkin=%s, checkout=%s",
            airbnb_thread_id,
            guest_name,
            checkin_date,
            checkout_date,
        )
    
    return updated


def _handle_cancellation(
    db: Session,
    parsed,
) -> None:
    """
    취소 이메일 처리: reservation_info의 status를 canceled로 변경
    
    reservation_code 기반으로 처리
    """
    repo = ReservationInfoRepository(db)
    reservation_code = getattr(parsed, "reservation_code", None)
    
    if not reservation_code:
        logger.warning(
            "Cannot cancel reservation: missing reservation_code"
        )
        return
    
    result = repo.cancel_by_reservation_code(reservation_code)
    if result:
        logger.info(
            "Canceled reservation: reservation_code=%s",
            reservation_code,
        )
    else:
        logger.warning(
            "Cannot find reservation to cancel: reservation_code=%s",
            reservation_code,
        )


def _handle_alteration_accepted(
    db: Session,
    parsed,
) -> None:
    """
    변경 수락 이메일 처리:
    1. reservation_code로 reservation_info 찾기
    2. pending alteration_request에서 요청된 날짜 가져오기
    3. reservation_info 날짜 업데이트
    4. alteration_request 상태 → accepted
    """
    res_repo = ReservationInfoRepository(db)
    alt_repo = AlterationRequestRepository(db)
    
    reservation_code = getattr(parsed, "reservation_code", None)
    
    if not reservation_code:
        logger.warning(
            "Alteration accepted but no reservation_code found"
        )
        return
    
    # 1. reservation_info 찾기
    reservation_info = res_repo.get_by_reservation_code(reservation_code)
    if not reservation_info:
        logger.warning(
            "Alteration accepted but reservation_info not found: reservation_code=%s",
            reservation_code,
        )
        return
    
    # 2. pending alteration_request 찾기
    alteration_request = alt_repo.get_pending_by_reservation_info_id(reservation_info.id)
    
    if alteration_request:
        # 3. alteration_request에서 요청된 날짜로 업데이트
        new_checkin = alteration_request.requested_checkin
        new_checkout = alteration_request.requested_checkout
        
        res_repo.update_dates_by_reservation_code(
            reservation_code=reservation_code,
            checkin_date=new_checkin,
            checkout_date=new_checkout,
        )
        
        # 4. alteration_request 상태 업데이트
        alt_repo.accept(alteration_request)
        
        # 5. reservation_info 상태 복원
        res_repo.set_status(reservation_info.id, ReservationStatus.CONFIRMED.value)
        
        logger.info(
            "Alteration accepted: reservation_code=%s, new_dates=%s~%s",
            reservation_code,
            new_checkin,
            new_checkout,
        )
    else:
        # alteration_request 없이 수락된 경우 (드문 케이스)
        # 이메일에서 파싱된 날짜로 업데이트 시도 (있으면)
        checkin_date = getattr(parsed, "checkin_date", None)
        checkout_date = getattr(parsed, "checkout_date", None)
        
        if checkin_date or checkout_date:
            res_repo.update_dates_by_reservation_code(
                reservation_code=reservation_code,
                checkin_date=checkin_date,
                checkout_date=checkout_date,
            )
            logger.info(
                "Alteration accepted (no pending request): reservation_code=%s",
                reservation_code,
            )
        else:
            logger.warning(
                "Alteration accepted but no pending request and no dates in email: "
                "reservation_code=%s",
                reservation_code,
            )


def _handle_alteration_requested(
    db: Session,
    parsed,
    gmail_message_id: str,
) -> None:
    """
    변경 요청 이메일 처리:
    1. listing_name + 기존 날짜로 reservation_info 찾기
    2. alteration_request 생성 (pending)
    3. reservation_info 상태 → alteration_requested
    """
    res_repo = ReservationInfoRepository(db)
    alt_repo = AlterationRequestRepository(db)
    
    # 파싱된 정보 추출
    listing_name = getattr(parsed, "ota_listing_name", None)
    original_checkin = getattr(parsed, "original_checkin", None)
    original_checkout = getattr(parsed, "original_checkout", None)
    requested_checkin = getattr(parsed, "requested_checkin", None)
    requested_checkout = getattr(parsed, "requested_checkout", None)
    alteration_id = getattr(parsed, "alteration_id", None)
    guest_name = getattr(parsed, "guest_name", None)
    
    if not original_checkin or not original_checkout:
        logger.warning(
            "Alteration requested but original dates not parsed: gmail_message_id=%s",
            gmail_message_id,
        )
        return
    
    if not requested_checkin or not requested_checkout:
        logger.warning(
            "Alteration requested but requested dates not parsed: gmail_message_id=%s",
            gmail_message_id,
        )
        return
    
    # 1. reservation_info 찾기 (listing_name + 기존 날짜)
    reservation_info = None
    if listing_name:
        reservation_info = res_repo.find_by_listing_and_dates(
            listing_name=listing_name,
            checkin_date=original_checkin,
            checkout_date=original_checkout,
        )
    
    reservation_info_id = reservation_info.id if reservation_info else None
    
    if not reservation_info:
        logger.warning(
            "Alteration requested but reservation_info not found: "
            "listing_name=%s, original_dates=%s~%s",
            listing_name[:50] if listing_name else None,
            original_checkin,
            original_checkout,
        )
    
    # 2. alteration_request 생성
    alt_repo.create(
        reservation_info_id=reservation_info_id,
        original_checkin=original_checkin,
        original_checkout=original_checkout,
        requested_checkin=requested_checkin,
        requested_checkout=requested_checkout,
        alteration_id=alteration_id,
        listing_name=listing_name,
        guest_name=guest_name,
        gmail_message_id=gmail_message_id,
    )
    
    # 3. reservation_info 상태 업데이트 (찾은 경우만)
    if reservation_info:
        res_repo.set_status(reservation_info.id, ReservationStatus.ALTERATION_REQUESTED.value)
    
    logger.info(
        "Alteration request created: original=%s~%s, requested=%s~%s, matched=%s",
        original_checkin,
        original_checkout,
        requested_checkin,
        requested_checkout,
        reservation_info_id is not None,
    )


def _handle_alteration_declined(
    db: Session,
    parsed,
) -> None:
    """
    변경 거절 이메일 처리:
    1. reservation_code로 reservation_info 찾기
    2. pending alteration_request 상태 → declined
    3. reservation_info 상태 → confirmed (원래대로)
    """
    res_repo = ReservationInfoRepository(db)
    alt_repo = AlterationRequestRepository(db)
    
    reservation_code = getattr(parsed, "reservation_code", None)
    
    if not reservation_code:
        logger.warning(
            "Alteration declined but no reservation_code found"
        )
        return
    
    # 1. reservation_info 찾기
    reservation_info = res_repo.get_by_reservation_code(reservation_code)
    if not reservation_info:
        logger.warning(
            "Alteration declined but reservation_info not found: reservation_code=%s",
            reservation_code,
        )
        return
    
    # 2. pending alteration_request 찾기 및 declined 처리
    alteration_request = alt_repo.get_pending_by_reservation_info_id(reservation_info.id)
    if alteration_request:
        alt_repo.decline(alteration_request)
    
    # 3. reservation_info 상태 복원
    res_repo.set_status(reservation_info.id, ReservationStatus.CONFIRMED.value)
    
    logger.info(
        "Alteration declined: reservation_code=%s",
        reservation_code,
    )


async def ingest_airbnb_parsed_messages(
    db: Session,
    parsed_messages: Iterable,
) -> None:
    """
    파싱된 Airbnb 메일들을 incoming_messages·reservation_info·conversations에 적재.
    
    v4 변경:
      - Intent 분류 제거 (Outcome Label은 draft 생성 시 처리)
      - MessageIntentLabelService 제거
      - Alteration Request 처리 추가 (requested/accepted/declined)
      - Lazy matching: reservation_code → airbnb_thread_id 업데이트
      - Fallback reservation_info 생성 제거
    """
    repo = IncomingMessageRepository(db)
    mapping_repo = OtaListingMappingRepository(db)

    for parsed in parsed_messages:
        # ParsedInternalMessage의 필드명은 'id' (gmail_message_id 아님)
        gmail_message_id = getattr(parsed, "id", None) or getattr(parsed, "gmail_message_id", None)
        if not gmail_message_id:
            continue

        email_type = getattr(parsed, "email_type", None)
        x_template = getattr(parsed, "x_template", None)
        reservation_code = getattr(parsed, "reservation_code", None)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 시스템 메일 처리 (reservation_code 기반, airbnb_thread_id 불필요)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # 1. 예약 확정: reservation_info 생성
        if email_type == "system_booking_confirmation":
            logger.info(
                "System email (booking confirmation): reservation_code=%s, x_template=%s",
                reservation_code,
                x_template,
            )
            _save_reservation_info(db, parsed, gmail_message_id)
            
            # ✅ 기존 conversation/incoming_message가 있으면 정보 업데이트
            # (MESSAGE 메일이 BOOKING_CONFIRMATION보다 먼저 처리된 경우 대비)
            airbnb_thread_id = getattr(parsed, "airbnb_thread_id", None)
            if airbnb_thread_id:
                _update_existing_conversation_info(db, parsed, airbnb_thread_id)
            
            continue
        
        # 2. 취소: reservation_info status → canceled
        if email_type == "system_cancellation":
            logger.info(
                "System email (cancellation): reservation_code=%s, x_template=%s",
                reservation_code,
                x_template,
            )
            _handle_cancellation(db, parsed)
            continue
        
        # 3. 변경 수락: alteration_request 처리 + reservation_info 날짜 업데이트
        if email_type == "system_alteration_accepted":
            logger.info(
                "System email (alteration accepted): reservation_code=%s, x_template=%s",
                reservation_code,
                x_template,
            )
            _handle_alteration_accepted(db, parsed)
            continue
        
        # 4. 변경 거절: alteration_request 상태만 업데이트
        if email_type == "system_alteration_declined":
            logger.info(
                "System email (alteration declined): reservation_code=%s, x_template=%s",
                reservation_code,
                x_template,
            )
            _handle_alteration_declined(db, parsed)
            continue
        
        # 5. 변경 요청: alteration_request 생성
        if email_type == "system_alteration_requested":
            logger.info(
                "System email (alteration requested): gmail_message_id=%s, x_template=%s",
                gmail_message_id,
                x_template,
            )
            _handle_alteration_requested(db, parsed, gmail_message_id)
            continue
        
        # 6. 완전 스킵 (후기 요청, 대금 지급 등)
        if email_type == "system_skip":
            logger.debug(
                "System email (skip): x_template=%s",
                x_template,
            )
            continue
        
        # 7. 예약 문의: reservation_info 없이 conversation/message만 생성
        if email_type == "booking_inquiry":
            logger.info(
                "Booking inquiry: gmail_message_id=%s, x_template=%s",
                gmail_message_id,
                x_template,
            )
            _handle_booking_inquiry(db, parsed, gmail_message_id, repo, mapping_repo)
            continue
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 예약 확정 후 게스트 메시지 처리 (airbnb_thread_id 필수)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        airbnb_thread_id = getattr(parsed, "airbnb_thread_id", None)
        if not airbnb_thread_id:
            logger.warning(
                "Airbnb ingestion: skip guest message without airbnb_thread_id gmail_message_id=%s",
                gmail_message_id,
            )
            continue

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 예약 확정 후 게스트 메시지 / unknown 처리
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        existing = repo.get_by_gmail_message_id(gmail_message_id)
        if existing is not None:
            logger.info(
                "Airbnb ingestion: skip already ingested gmail_message_id=%s (incoming_message_id=%s)",
                gmail_message_id,
                existing.id,
            )
            continue

        decoded_text_body = getattr(parsed, "decoded_text_body", None)
        decoded_html_body = getattr(parsed, "decoded_html_body", None)
        sender_role = getattr(parsed, "sender_role", None)

        origin = classify_airbnb_message_origin(
            decoded_text_body=decoded_text_body,
            decoded_html_body=decoded_html_body,
            subject=getattr(parsed, "subject", None),
            snippet=getattr(parsed, "snippet", None),
            sender_role=sender_role,
        )

        # pure_guest_message: 이미 분리된 메시지는 decoded_text_body 자체가 순수 메시지
        if sender_role:
            pure_guest_message = decoded_text_body or ""
        else:
            pure_guest_message = extract_guest_message_segment(decoded_text_body or "")

        # ✅ Intent 분류 제거됨 (v3)
        # Outcome Label은 draft 생성 시 LLM이 판단

        property_code = getattr(parsed, "property_code", None)
        ota = getattr(parsed, "ota", None)
        ota_listing_id = getattr(parsed, "ota_listing_id", None)
        if not property_code and ota and ota_listing_id:
            try:
                mapping = mapping_repo.get_by_ota_listing_id(
                    ota=ota,
                    listing_id=ota_listing_id,
                    active_only=True,
                )
                if mapping is not None:
                    property_code = mapping.property_code
            except Exception as exc:
                logger.warning(
                    "Failed to map (ota, listing_id) to property_code: ota=%s listing_id=%s err=%s",
                    ota,
                    ota_listing_id,
                    exc,
                )

        msg = repo.create_from_parsed(
            gmail_message_id=gmail_message_id,
            airbnb_thread_id=airbnb_thread_id,
            subject=getattr(parsed, "subject", None),
            from_email=getattr(parsed, "from_email", None),
            reply_to=getattr(parsed, "reply_to", None),
            received_at=getattr(parsed, "received_at", None),
            origin=origin,
            intent_result=None,  # Intent 제거됨
            pure_guest_message=pure_guest_message,
            ota=ota,
            ota_listing_id=ota_listing_id,
            ota_listing_name=getattr(parsed, "ota_listing_name", None),
            property_code=property_code,
            guest_name=getattr(parsed, "guest_name", None),
            checkin_date=getattr(parsed, "checkin_date", None),
            checkout_date=getattr(parsed, "checkout_date", None),
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Lazy Matching: pending 상태의 reservation_info에 airbnb_thread_id 업데이트
        # (CSV 수기 입력으로 airbnb_thread_id 없이 생성된 reservation_info 대응)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        checkin_date = getattr(parsed, "checkin_date", None)
        guest_name = getattr(parsed, "guest_name", None)
        
        reservation_info_repo = ReservationInfoRepository(db)
        
        # 이미 이 airbnb_thread_id로 연결된 reservation_info가 있으면 스킵
        existing_info = reservation_info_repo.get_by_airbnb_thread_id(airbnb_thread_id)
        
        if not existing_info and property_code and checkin_date:
            # pending 상태인 CSV 수기 입력 데이터에서 매칭 시도
            matched = reservation_info_repo.update_pending_reservation_by_lazy_match(
                checkin_date=checkin_date,
                property_code=property_code,
                guest_name=guest_name,
                airbnb_thread_id=airbnb_thread_id,
            )
            if matched:
                logger.info(
                    "Lazy matching: matched reservation_code=%s → airbnb_thread_id=%s",
                    matched.reservation_code,
                    airbnb_thread_id,
                )
        
        # NOTE: Fallback reservation_info 생성 제거 (v4)
        # reservation_info는 오직 BOOKING_CONFIRMATION 메일에서만 생성됨

        # Conversation upsert
        conversation = None
        if not property_code:
            logger.warning(
                "Airbnb ingestion: skip conversation upsert (no property_code) gmail_message_id=%s",
                gmail_message_id,
            )
        else:
            conversation = ConversationService(db).upsert_for_thread(
                channel=ConversationChannel.gmail,
                airbnb_thread_id=msg.airbnb_thread_id,
                last_message_id=msg.id,
                property_code=property_code,
                received_at=msg.received_at,
            )

        # 메시지 타입별 후처리 (Staff Notification, Draft 생성 등)
        process_result = process_message_after_ingestion(
            db=db,
            message=msg,
            email_type=email_type,
            conversation=conversation,
        )
        if process_result.processed:
            logger.info(
                "Message post-processing completed: message_id=%s, email_type=%s, "
                "draft_created=%s, notification_created=%s",
                msg.id,
                email_type,
                process_result.draft_created,
                process_result.notification_created,
            )

        # ✅ MessageIntentLabelService 호출 제거됨 (v3)
