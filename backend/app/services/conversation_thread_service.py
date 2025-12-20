# backend/app/services/conversation_thread_service.py
"""
Conversation Thread Service (v3 - Outcome Label 지원)

변경사항:
- DraftService.upsert_latest에 outcome_label 파라미터 추가
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.domain.models.conversation import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    DraftReply,
    SafetyStatus,
    SendAction,
    SendActionLog,
)
from app.domain.models.incoming_message import IncomingMessage, MessageDirection
from app.domain.intents import MessageActor


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def apply_safety_to_conversation(conversation: Conversation, safety: SafetyStatus) -> None:
    """Safety 상태에 따라 Conversation 상태를 업데이트 (v4: review도 발송 허용)"""
    conversation.safety_status = safety
    if safety == SafetyStatus.pass_:
        conversation.status = ConversationStatus.ready_to_send
    elif safety == SafetyStatus.review:
        # v4: review도 발송 가능 (사람이 확인 후 발송)
        conversation.status = ConversationStatus.ready_to_send
    else:
        conversation.status = ConversationStatus.blocked


@dataclass
class ConversationService:
    """Conversation CRUD 서비스"""
    db: Session

    def upsert_for_thread(
        self, 
        *, 
        channel: ConversationChannel, 
        airbnb_thread_id: str,
        last_message_id: int | None = None,
        property_code: str | None = None,
        received_at: datetime | None = None,
    ) -> Conversation:
        """
        Thread ID로 Conversation을 조회하거나, 없으면 생성.
        (Gmail + Airbnb airbnb_thread_id) 조합으로 유니크하게 관리
        """
        stmt = (
            select(Conversation)
            .where(Conversation.channel == channel)
            .where(Conversation.airbnb_thread_id == airbnb_thread_id)
        )
        existing = self.db.execute(stmt).scalar_one_or_none()

        now = _now_utc()

        if existing:
            # last_message_id가 주어지면 업데이트
            if last_message_id is not None:
                existing.last_message_id = last_message_id
            # property_code가 없거나 새로 주어지면 업데이트
            if property_code and not existing.property_code:
                existing.property_code = property_code
            # 새 메시지가 오면 읽지 않음으로 변경
            existing.is_read = False
            existing.updated_at = now
            existing.last_message_at = received_at or now
            if received_at:
                existing.received_at = received_at
            self.db.add(existing)
            self.db.flush()
            return existing

        conv = Conversation(
            channel=channel,
            airbnb_thread_id=airbnb_thread_id,
            last_message_id=last_message_id,
            status=ConversationStatus.new,
            property_code=property_code,
            received_at=received_at,
            last_message_at=received_at or now,
            is_read=False,
        )
        self.db.add(conv)
        self.db.flush()
        return conv

    def mark_as_read(self, *, conversation_id: uuid.UUID) -> bool:
        """Conversation을 읽음 상태로 변경"""
        conv = self.db.get(Conversation, conversation_id)
        if conv is None:
            return False
        conv.is_read = True
        conv.updated_at = _now_utc()
        self.db.add(conv)
        self.db.flush()
        return True

    def mark_as_unread(self, *, conversation_id: uuid.UUID) -> bool:
        """Conversation을 읽지 않음 상태로 변경"""
        conv = self.db.get(Conversation, conversation_id)
        if conv is None:
            return False
        conv.is_read = False
        conv.updated_at = _now_utc()
        self.db.add(conv)
        self.db.flush()
        return True

    def mark_as_complete(self, *, conversation_id: uuid.UUID) -> bool:
        """Conversation을 완료 상태로 변경"""
        conv = self.db.get(Conversation, conversation_id)
        if conv is None:
            return False
        conv.status = ConversationStatus.complete
        conv.updated_at = _now_utc()
        self.db.add(conv)
        self.db.flush()
        return True


@dataclass
class DraftService:
    """Draft Reply 관리 서비스 (v3)"""
    db: Session

    def generate_draft(self, *, airbnb_thread_id: str) -> str:
        """간단한 기본 Draft 생성 (LLM 없이)"""
        msgs = self.db.execute(
            select(IncomingMessage)
            .where(IncomingMessage.airbnb_thread_id == airbnb_thread_id)
            .order_by(asc(IncomingMessage.received_at), asc(IncomingMessage.id))
        ).scalars().all()

        last_guest = None
        for m in reversed(msgs):
            if m.direction == MessageDirection.incoming and m.sender_actor == MessageActor.GUEST:
                if (m.pure_guest_message or "").strip():
                    last_guest = m
                    break

        if last_guest:
            guest_text = (last_guest.pure_guest_message or "").strip()
            return (
                f'안녕하세요! 문의 주셔서 감사합니다. 말씀하신 내용("{guest_text[:120]}") 확인했습니다. '
                "추가로 필요한 정보가 있으면 알려주시면 바로 도와드리겠습니다."
            )
        return "안녕하세요! 문의 주셔서 감사합니다. 내용을 확인하고 안내드리겠습니다."

    def upsert_latest(
        self, 
        *, 
        conversation: Conversation, 
        content: str, 
        safety: SafetyStatus,
        outcome_label: Optional[Dict[str, Any]] = None,
        is_user_edit: bool = False,  # ✅ v4 추가: 사용자 수정 여부
    ) -> DraftReply:
        """
        Draft를 생성하거나 최신 Draft를 업데이트 (v4)
        
        Args:
            conversation: 연결된 Conversation
            content: 초안 내용
            safety: Safety 상태
            outcome_label: Outcome Label 4축 + 근거 (선택)
            is_user_edit: True면 사용자 수정으로 처리 (수정 이력 기록)
        """
        latest = self.db.execute(
            select(DraftReply)
            .where(DraftReply.conversation_id == conversation.id)
            .order_by(desc(DraftReply.created_at))
            .limit(1)
        ).scalar_one_or_none()

        if latest is None:
            # 최초 생성: original_content에도 저장
            dr = DraftReply(
                conversation_id=conversation.id,
                airbnb_thread_id=conversation.airbnb_thread_id,
                content=content,
                original_content=content,  # ✅ v4: 원본 저장
                is_edited=False,
                safety_status=safety,
                outcome_label=outcome_label,
            )
            self.db.add(dr)
            self.db.flush()
            return dr

        # 기존 Draft 업데이트
        if is_user_edit and latest.content != content:
            # 사용자가 내용을 수정한 경우
            if not latest.is_edited:
                # 최초 수정: original_content가 없으면 현재 content 저장
                if not latest.original_content:
                    latest.original_content = latest.content
            
            latest.is_edited = True
            latest.human_override = {
                "applied": True,
                "original_content": latest.original_content,
                "edited_at": _now_utc().isoformat(),
                "actor": "staff",  # TODO: 실제 사용자 ID
            }
        elif not is_user_edit:
            # LLM 재생성: original_content 갱신, is_edited 리셋
            latest.original_content = content
            latest.is_edited = False
            latest.human_override = None
        
        latest.content = content
        latest.airbnb_thread_id = conversation.airbnb_thread_id
        latest.safety_status = safety
        latest.outcome_label = outcome_label
        latest.updated_at = _now_utc()
        self.db.add(latest)
        self.db.flush()
        return latest

    def get_latest(self, *, conversation_id: uuid.UUID) -> DraftReply | None:
        """Conversation의 최신 Draft 조회"""
        return self.db.execute(
            select(DraftReply)
            .where(DraftReply.conversation_id == conversation_id)
            .order_by(desc(DraftReply.created_at))
            .limit(1)
        ).scalar_one_or_none()

    def add_human_override(
        self,
        *,
        draft_id: uuid.UUID,
        reason: str,
        actor: str,
    ) -> Optional[DraftReply]:
        """
        운영자 오버라이드 추가 (v3)
        
        원본 outcome_label은 보존하고, human_override만 기록
        """
        draft = self.db.get(DraftReply, draft_id)
        if draft is None:
            return None
        
        draft.human_override = {
            "applied": True,
            "reason": reason,
            "actor": actor,
            "timestamp": _now_utc().isoformat(),
        }
        draft.updated_at = _now_utc()
        self.db.add(draft)
        self.db.flush()
        return draft


@dataclass
class SafetyGuardService:
    """Safety 평가 서비스 (v4: 한국어 키워드 확장)"""
    db: Session

    def evaluate_text(self, *, text: str) -> tuple[SafetyStatus, list[str]]:
        """
        텍스트의 Safety를 평가.
        
        Returns:
            (SafetyStatus, 트리거된 키워드 목록)
        """
        import re
        
        lower = text.lower()
        triggered: list[str] = []

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 차단 키워드 (발송 불가)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        block_keywords = [
            # 영어
            "suicide", "kill", "weapon", "gun", "bomb",
            "illegal", "drugs", "cvv",
            # 한국어 - 자해/폭력
            "자살", "자해", "죽이", "살인", "폭행",
            # 한국어 - 불법/사기
            "불법", "마약", "사기", "해킹",
        ]
        for kw in block_keywords:
            if kw in lower or kw in text:
                triggered.append(kw)
        if triggered:
            return SafetyStatus.block, triggered

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 검토 필요 키워드 (수동 확인 필요)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        review_keywords = [
            # 영어
            "phone", "kakao", "whatsapp", "email",
            "address", "account number",
            # 한국어 - 연락처
            "전화", "핸드폰", "휴대폰", "휴대전화", "연락처",
            "카카오", "카톡", "텔레그램", "라인",
            # 한국어 - 금융
            "계좌", "입금", "송금", "이체", "결제",
            "현금", "무통장",
            # 한국어 - 주소
            "주소", "우편번호",
            # 한국어 - 개인정보
            "주민번호", "주민등록",
        ]
        for kw in review_keywords:
            if kw in lower or kw in text:
                triggered.append(kw)
        
        # 정규식 패턴 (전화번호, 계좌번호)
        patterns = [
            (r"01[0-9]-?\d{3,4}-?\d{4}", "전화번호 패턴"),
            (r"\d{3}-\d{2,4}-\d{4,6}", "계좌번호 패턴"),
        ]
        for pattern, label in patterns:
            if re.search(pattern, text):
                triggered.append(label)
        
        if triggered:
            return SafetyStatus.review, triggered

        return SafetyStatus.pass_, []


@dataclass
class SendLogService:
    """발송 로그 서비스"""
    db: Session

    def log_action(
        self,
        *,
        conversation: Conversation,
        action: SendAction,
        content_sent: str | None = None,
        message_id: int | None = None,
        actor: str = "system",
        payload_json: dict | None = None,
    ) -> SendActionLog:
        """발송 액션을 로그에 기록"""
        log = SendActionLog(
            conversation_id=conversation.id,
            airbnb_thread_id=conversation.airbnb_thread_id,
            property_code=conversation.property_code or "",
            message_id=message_id,
            action=action,
            content_sent=content_sent,
            actor=actor,
            payload_json=payload_json or {},
        )
        self.db.add(log)
        self.db.flush()
        return log
