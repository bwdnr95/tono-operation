# backend/app/services/message_processor_service.py
"""
이메일 인제스트 후 타입별 후처리를 담당하는 서비스 (v3).

변경사항:
- async AutoReplyService 연동
- Outcome Label 저장 (draft_replies에)
- suggest_reply_for_message_sync 제거

책임:
- guest_message: (현재는 job에서 처리, 향후 여기로 통합 가능)
- booking_inquiry: LLM 초안 생성 + Staff Notification (발송 불가)
- system_*: skip
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.domain.models.conversation import Conversation
from app.domain.models.incoming_message import IncomingMessage
from app.domain.models.reservation_info import ReservationInfo, ReservationStatus
from app.domain.models.staff_notification import StaffNotification
from app.repositories.staff_notification_repository import StaffNotificationRepository
from app.services.conversation_thread_service import DraftService, SafetyGuardService


logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """후처리 결과"""
    processed: bool
    email_type: str
    draft_created: bool = False
    notification_created: bool = False
    skip_reason: Optional[str] = None


class MessageProcessorService:
    """
    이메일 인제스트 후 타입별 후처리를 담당.
    """
    
    def __init__(self, db: Session):
        self._db = db
    
    async def process_after_ingestion_async(
        self,
        *,
        message: IncomingMessage,
        email_type: str,
        conversation: Optional[Conversation] = None,
    ) -> ProcessResult:
        """
        이메일 타입에 따라 적절한 후처리 수행 (async).
        """
        # 시스템 메일은 스킵
        if email_type and email_type.startswith("system_"):
            return ProcessResult(
                processed=False,
                email_type=email_type,
                skip_reason="system_email",
            )
        
        # booking_inquiry 처리
        if email_type == "booking_inquiry":
            return await self._process_booking_inquiry_async(
                message=message,
                conversation=conversation,
            )
        
        # guest_message는 현재 job에서 처리 (향후 통합 가능)
        if email_type == "guest_message":
            return ProcessResult(
                processed=False,
                email_type=email_type,
                skip_reason="handled_by_auto_reply_job",
            )
        
        # unknown 타입
        return ProcessResult(
            processed=False,
            email_type=email_type or "unknown",
            skip_reason="unknown_email_type",
        )
    
    def process_after_ingestion(
        self,
        *,
        message: IncomingMessage,
        email_type: str,
        conversation: Optional[Conversation] = None,
    ) -> ProcessResult:
        """
        이메일 타입에 따라 적절한 후처리 수행 (sync wrapper).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            # 이미 이벤트 루프가 실행 중이면 새 태스크로 실행
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.process_after_ingestion_async(
                        message=message,
                        email_type=email_type,
                        conversation=conversation,
                    )
                )
                return future.result()
        else:
            return asyncio.run(
                self.process_after_ingestion_async(
                    message=message,
                    email_type=email_type,
                    conversation=conversation,
                )
            )
    
    async def _process_booking_inquiry_async(
        self,
        *,
        message: IncomingMessage,
        conversation: Optional[Conversation],
    ) -> ProcessResult:
        """
        예약 문의(BOOKING_INITIAL_INQUIRY) 처리 (async).
        
        - Reply-To가 없어 이메일 답변 불가
        - LLM 초안 생성하여 Draft에 저장 (호스트가 복사해서 에어비앤비 앱에서 사용)
        - Staff Notification 생성
        - ReservationInfo 생성 (status=inquiry)
        """
        draft_created = False
        notification_created = False
        
        # 0. ReservationInfo 생성/업데이트 (문의 정보 저장)
        if message.airbnb_thread_id:
            try:
                existing = self._db.execute(
                    select(ReservationInfo)
                    .where(ReservationInfo.airbnb_thread_id == message.airbnb_thread_id)
                ).scalar_one_or_none()
                
                if existing:
                    # 기존 레코드가 있으면 업데이트 (단, confirmed/canceled는 덮어쓰지 않음)
                    if existing.status not in (
                        ReservationStatus.CONFIRMED.value,
                        ReservationStatus.CANCELED.value,
                    ):
                        if message.guest_name:
                            existing.guest_name = message.guest_name
                        if message.checkin_date:
                            existing.checkin_date = message.checkin_date
                        if message.checkout_date:
                            existing.checkout_date = message.checkout_date
                        if message.property_code:
                            existing.property_code = message.property_code
                        logger.info(
                            "Updated ReservationInfo for inquiry: airbnb_thread_id=%s",
                            message.airbnb_thread_id,
                        )
                else:
                    # 새로 생성
                    # action_url 생성
                    action_url = None
                    if message.airbnb_thread_id:
                        action_url = f"https://www.airbnb.co.kr/hosting/thread/{message.airbnb_thread_id}?thread_type=home_booking"
                    
                    new_info = ReservationInfo(
                        airbnb_thread_id=message.airbnb_thread_id,
                        status=ReservationStatus.INQUIRY.value,
                        guest_name=message.guest_name,
                        checkin_date=message.checkin_date,
                        checkout_date=message.checkout_date,
                        property_code=message.property_code,
                        listing_id=message.ota_listing_id,
                        listing_name=message.ota_listing_name,
                        guest_message=message.pure_guest_message,
                        source_template="BOOKING_INITIAL_INQUIRY",
                        gmail_message_id=str(message.id) if message.id else None,
                        action_url=action_url,
                    )
                    self._db.add(new_info)
                    logger.info(
                        "Created ReservationInfo for inquiry: airbnb_thread_id=%s, guest=%s",
                        message.airbnb_thread_id,
                        message.guest_name,
                    )
                
                self._db.flush()
            except Exception as e:
                logger.error(
                    "Failed to create/update ReservationInfo for inquiry: airbnb_thread_id=%s, error=%s",
                    message.airbnb_thread_id,
                    e,
                )
        
        # 1. Staff Notification 생성
        try:
            notification = StaffNotification(
                property_code=message.property_code,
                ota=message.ota or "airbnb",
                guest_name=message.guest_name,
                checkin_date=str(message.checkin_date) if message.checkin_date else None,
                checkout_date=str(message.checkout_date) if message.checkout_date else None,
                message_summary=(message.pure_guest_message or "")[:120],
                follow_up_actions=[
                    "📱 에어비앤비 앱에서 직접 답변 필요",
                    "⚠️ 이메일 답변 불가 (예약 문의)",
                ],
            )
            
            notif_repo = StaffNotificationRepository(self._db)
            notif_repo.create_from_domain(notification, message_id=message.id)
            notification_created = True
            
            logger.info(
                "Booking inquiry notification created: message_id=%s, airbnb_thread_id=%s",
                message.id,
                message.airbnb_thread_id,
            )
        except Exception as e:
            logger.error(
                "Failed to create booking inquiry notification: message_id=%s, error=%s",
                message.id,
                e,
            )
        
        # 2. LLM 초안 생성 (conversation이 있는 경우)
        if conversation:
            try:
                draft_created = await self._create_inquiry_draft_async(
                    message=message,
                    conversation=conversation,
                )
            except Exception as e:
                logger.error(
                    "Failed to create inquiry draft: message_id=%s, error=%s",
                    message.id,
                    e,
                )
        
        return ProcessResult(
            processed=True,
            email_type="booking_inquiry",
            draft_created=draft_created,
            notification_created=notification_created,
        )
    
    async def _create_inquiry_draft_async(
        self,
        *,
        message: IncomingMessage,
        conversation: Conversation,
    ) -> bool:
        """
        예약 문의에 대한 Draft 생성 (async).
        
        AutoReplyService v3를 통해 LLM 기반 응답 생성.
        Outcome Label도 함께 저장.
        """
        from app.services.auto_reply_service import AutoReplyService
        from app.adapters.llm_client import get_openai_client
        
        # AutoReplyService v3로 LLM 기반 응답 생성
        openai_client = get_openai_client()
        auto_reply_service = AutoReplyService(self._db, openai_client=openai_client)
        
        try:
            suggestion = await auto_reply_service.suggest_reply_for_message(
                message_id=message.id,
                locale="ko",
                property_code=message.property_code,
            )
            
            if suggestion and suggestion.reply_text:
                draft_content = suggestion.reply_text
                outcome_label_dict = suggestion.outcome_label.to_dict() if suggestion.outcome_label else None
                
                logger.info(
                    "LLM draft generated for inquiry: message_id=%s, mode=%s, safety=%s",
                    message.id,
                    suggestion.generation_mode,
                    suggestion.outcome_label.safety_outcome.value if suggestion.outcome_label else "N/A",
                )
            else:
                # LLM 실패 시 템플릿 폴백
                draft_content = self._generate_inquiry_template_response(
                    guest_name=message.guest_name or "게스트",
                    guest_text=(message.pure_guest_message or "").strip(),
                    checkin_date=message.checkin_date,
                    checkout_date=message.checkout_date,
                )
                outcome_label_dict = None
                logger.warning(
                    "LLM draft failed, using template: message_id=%s",
                    message.id,
                )
        except Exception as e:
            # 에러 시 템플릿 폴백
            logger.error(
                "LLM draft error, using template: message_id=%s, error=%s",
                message.id,
                e,
            )
            draft_content = self._generate_inquiry_template_response(
                guest_name=message.guest_name or "게스트",
                guest_text=(message.pure_guest_message or "").strip(),
                checkin_date=message.checkin_date,
                checkout_date=message.checkout_date,
            )
            outcome_label_dict = None
        
        # Safety check (기존 SafetyGuard도 유지)
        guard = SafetyGuardService(db=self._db)
        safety, _ = guard.evaluate_text(text=draft_content)
        
        # Draft 저장 (Outcome Label 포함)
        draft_service = DraftService(db=self._db)
        draft_service.upsert_latest(
            conversation=conversation,
            content=draft_content,
            safety=safety,
            outcome_label=outcome_label_dict,  # ✅ Outcome Label 저장
        )
        
        logger.info(
            "Inquiry draft created: conversation_id=%s, airbnb_thread_id=%s, has_outcome=%s",
            conversation.id,
            conversation.airbnb_thread_id,
            outcome_label_dict is not None,
        )
        
        return True
    
    def _generate_inquiry_template_response(
        self,
        *,
        guest_name: str,
        guest_text: str,
        checkin_date,
        checkout_date,
    ) -> str:
        """
        예약 문의에 대한 템플릿 응답 생성 (폴백용).
        """
        date_info = ""
        if checkin_date and checkout_date:
            date_info = f" ({checkin_date} ~ {checkout_date})"
        
        # 메시지 내용이 있으면 포함
        message_ref = ""
        if guest_text:
            message_ref = f'\n\n말씀하신 "{guest_text[:100]}..." 관련하여 '
        
        return (
            f"안녕하세요, {guest_name}님! 숙소에 관심 가져주셔서 감사합니다.{date_info}"
            f"{message_ref}"
            "\n\n문의하신 내용 확인했습니다. "
            "추가로 궁금하신 점이 있으시면 편하게 말씀해 주세요. "
            "예약을 진행해 주시면 더 자세한 안내를 드리겠습니다. 감사합니다! 😊"
        )


# 편의 함수
def process_message_after_ingestion(
    *,
    db: Session,
    message: IncomingMessage,
    email_type: str,
    conversation: Optional[Conversation] = None,
) -> ProcessResult:
    """
    이메일 인제스트 후 후처리를 수행하는 편의 함수.
    """
    service = MessageProcessorService(db)
    return service.process_after_ingestion(
        message=message,
        email_type=email_type,
        conversation=conversation,
    )


async def process_message_after_ingestion_async(
    *,
    db: Session,
    message: IncomingMessage,
    email_type: str,
    conversation: Optional[Conversation] = None,
) -> ProcessResult:
    """
    이메일 인제스트 후 후처리를 수행하는 편의 함수 (async).
    """
    service = MessageProcessorService(db)
    return await service.process_after_ingestion_async(
        message=message,
        email_type=email_type,
        conversation=conversation,
    )
