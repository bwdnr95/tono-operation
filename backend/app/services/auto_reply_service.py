# backend/app/services/auto_reply_service.py
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, asdict, is_dataclass

from typing import Optional, Tuple, Any, Dict

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain.intents import (
    MessageIntent,
    FineGrainedIntent,
    MessageActor,
    MessageActionability,
)
from app.domain.intents.auto_action import MessageActionType
from app.domain.intents.types import IntentLabelSource  # ✅ 여기! (backend. 빠짐)

from app.repositories.messages import IncomingMessageRepository
from app.repositories.property_profile_repository import PropertyProfileRepository
from app.repositories.auto_reply_template_repository import AutoReplyTemplateRepository
from app.repositories.staff_notification_repository import StaffNotificationRepository
from app.repositories.auto_reply_log_repository import AutoReplyLogRepository
from app.repositories.message_intent_labels import (
    MessageIntentLabelRepository,
)  # ✅ fine_intent 라벨 기록용

from app.services.airbnb_intent_classifier import (
    AirbnbIntentClassifier,
    HybridIntentResult,
)
from app.services.intent_action_decider import IntentActionDecider
from app.services.reply_context_builder import ReplyContextBuilder, ReplyContext
from app.services.llm_intent_classifier import FineGrainedIntentResult
from app.services.closing_message_detector import ClosingMessageDetector
from app.domain.models.staff_notification import StaffNotification
from app.core.config import settings
from app.domain.models.incoming_message import IncomingMessage

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class AutoReplySuggestion:
    message_id: int
    intent: MessageIntent
    fine_intent: Optional[FineGrainedIntent]
    intent_confidence: float
    reply_text: str
    template_id: Optional[int]
    # "template" | "llm_with_template" | "llm_no_template" | "no_template_fallback"
    generation_mode: str
    action: MessageActionType
    allow_auto_send: bool
    is_ambiguous: bool


class AutoReplyService:
    """
    TONO AutoReply 엔진.

    역할:
      1) 메시지 Intent (primary + fine)를 확보
      2) PropertyProfile 기반 ReplyContext 구성
      3) 템플릿/LLM 하이브리드로 답변 텍스트 생성
      4) Intent → ActionDecider로 액션 결정 (AUTO_REPLY / STAFF_ALERT 등)
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._msg_repo = IncomingMessageRepository(db)
        self._property_repo = PropertyProfileRepository(db)
        self._template_repo = AutoReplyTemplateRepository(db)

        self._intent_classifier = AirbnbIntentClassifier()
        self._action_decider = IntentActionDecider()
        self._context_builder = ReplyContextBuilder(db)

        # 🔽 기존에는 self._llm 이라는 필드를 상정하고 있었는데,
        # 현재 AutoReplyService는 내부에서 직접 OpenAI SDK를 사용하고 있으며
        # LLMClient 인스턴스를 공유하지 않는다.
        # ClosingMessageDetector도 LLMClient 의존성을 제거했기 때문에
        # 여기서는 단순 기본 인스턴스를 생성해서 사용하면 된다.
        self.closing_detector = ClosingMessageDetector()

        self._auto_reply_log_repo = AutoReplyLogRepository(db)
        self._intent_label_repo = MessageIntentLabelRepository(db)
        self._auto_reply_mode = getattr(settings, "AUTO_REPLY_MODE", "AUTOPILOT").upper()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def _build_staff_notification(
        self,
        *,
        message,
        context: ReplyContext,
        primary_intent: MessageIntent,
        fine_intent: Optional[FineGrainedIntent],
        reply_text: str,
    ) -> Optional[StaffNotification]:
        """
        게스트 메시지 + Intent + ReplyContext를 기반으로
        운영팀 Follow-up 알림(StaffNotification)을 생성한다.
        """

        actions = await self._extract_follow_up_actions_with_llm(
            message_text=message.pure_guest_message or "",
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            reply_text=reply_text,
            context=context,
        )

        if not actions:
            return None

        # 🔹 guest_name 최대한 채우기
        guest_name = getattr(message, "guest_name", None)

        # 필요하면 여기서 from_email 파싱 등 추가 가능
        # ex) "홍길동 via Airbnb <xxx@xxx>" 형태에서 앞부분만 떼는 로직 등

        checkin_date = getattr(message, "checkin_date", None)
        checkout_date = getattr(message, "checkout_date", None)

        return StaffNotification(
            property_code=context.property_code,
            ota=message.ota,
            guest_name=guest_name,
            checkin_date=str(checkin_date) if checkin_date else None,
            checkout_date=str(checkout_date) if checkout_date else None,
            message_summary=(message.pure_guest_message or "")[:120],
            follow_up_actions=actions,
        )
    def _closing_static_reply(self, locale: str) -> tuple[str, str]:
        """
        '대화 종료용 감사 인사' 고정 답변을 반환.
        - closing_detector 가 is_closing=True 인 경우에만 사용.
        - (reply_text, generation_mode) 튜플로 반환.
        """
        if locale.startswith("ko"):
            reply_text = (
                "감사합니다! 일정 간 행복만 가득하시길 기도하겠습니다 :) "
                "다른 문의사항 있으시면 언제든지 연락 남겨주세요!"
            )
        else:
            reply_text = (
                "Thank you! Wishing you nothing but happiness throughout your stay :) "
                "If you have any questions, please feel free to contact us anytime!"
            )

        # generation_mode는 로그/분석용 태그
        return reply_text, "closing_static"

    async def suggest_reply_for_message(
        self,
        *,
        message_id: int,
        ota: Optional[str] = None,
        locale: str = "ko",
        property_code: Optional[str] = None,
        use_llm: bool = True,
    ) -> Optional[AutoReplySuggestion]:
        """
        메시지 1건에 대한 자동응답 초안을 만든다.
        - 실제 발송은 이 결과를 보고 프론트/운영툴에서 결정.
        """

        msg = self._msg_repo.get(message_id)
        if not msg:
            return None

        # ✅ 추가: 게스트가 아니거나, 답장이 필요 없는 메시지는 자동응답 대상에서 제외
        if msg.sender_actor != MessageActor.GUEST:
            logger.info(
                "AUTOREPLY_SKIP(non-guest): message_id=%s actor=%s",
                message_id,
                msg.sender_actor,
            )
            return None

        if msg.actionability != MessageActionability.NEEDS_REPLY:
            logger.info(
                "AUTOREPLY_SKIP(non-needs-reply): message_id=%s actionability=%s",
                message_id,
                msg.actionability,
            )
            return None

        # 특별 케이스: 종료 인사 감지
        closing = await self.closing_detector.detect(msg.pure_guest_message)

        if closing.is_closing:
            primary_intent = MessageIntent.THANKS_OR_GOOD_REVIEW
            fine_intent = FineGrainedIntent.GENERAL_THANKS
            reply_text, generation_mode = self._closing_static_reply(locale=locale)

            return AutoReplySuggestion(
                message_id=message_id,
                intent=primary_intent,
                fine_intent=fine_intent,
                intent_confidence=0.95,
                reply_text=reply_text,
                action=MessageActionType.AUTO_REPLY,
                allow_auto_send=True,
                template_id=None,
                is_ambiguous=False,
                generation_mode=generation_mode,
            )

        # 1) Intent (primary + fine) 확보
        primary_intent, fine_intent, intent_conf, is_ambiguous = self._ensure_intent(
            msg_id=message_id,
            ota=ota or msg.ota,
        )

        # Intent가 정말로 OTHER이고, pure_guest_message도 거의 비어 있으면 → 굳이 응답 만들 필요 없음
        if primary_intent == MessageIntent.OTHER and not (msg.pure_guest_message or "").strip():
            return None

        # 2) ReplyContext 구성 (PropertyProfile selection 포함)
        context = self._context_builder.build_for_message(
            message_id=message_id,
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            locale=locale,
            explicit_property_code=property_code,
        )

        # OTA → channel 매핑 (지금은 단순히 ota 그대로 사용, 없으면 'unknown')
        channel = (ota or msg.ota or "unknown") or "unknown"

        # 3) Intent 기반 템플릿 선택 (fine_intent, property_code, channel, confidence까지 고려)
        template = self._template_repo.get_best_template_for_intent(
            intent=primary_intent,
            fine_intent=fine_intent,
            locale=locale,
            channel=channel,                 # 예: 'airbnb'
            property_code=context.property_code,
            intent_confidence=intent_conf,
        )

        # 게스트 메시지 텍스트 (LLM 컨텍스트용)
        guest_message = (
            (msg.pure_guest_message or "").strip()
            or (getattr(msg, "snippet", "") or "").strip()
            or (getattr(msg, "text_body", "") or "").strip()
        )

        # 4) 템플릿/LLM 조합으로 최종 reply_text 생성
        #    - 원칙: LLM + property_profile이 항상 주인공
        #    - 템플릿은 있을 경우 "정책/톤 가이드"로만 사용
        if use_llm:
            if template:
                # ✅ LLM + 템플릿 + property_profile
                reply_text = await self._generate_with_llm_and_template(
                    guest_message=guest_message,
                    template_text=template.body_template,
                    context=context,
                    locale=locale,
                )
                generation_mode = "llm_with_template"
            else:
                # ✅ LLM + property_profile only
                reply_text = await self._generate_with_llm_without_template(
                    guest_message=guest_message,
                    context=context,
                    locale=locale,
                )
                generation_mode = "llm_no_template"
        else:
            # ⚠ LLM 미사용 모드는 예외적 상황(HITL 디버깅 등)에서만 사용
            if template:
                reply_text = template.body_template
                generation_mode = "template_only"
            else:
                reply_text = self._default_fallback_reply(
                    locale=locale,
                    primary_intent=primary_intent,
                )
                generation_mode = "no_template_fallback"

        # 5) Intent → Action 결정 (자동발송 가능 여부 등)
        action_decision = self._action_decider.decide(
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            intent_confidence=intent_conf,
            is_ambiguous=is_ambiguous,
        )

        suggestion = AutoReplySuggestion(
            message_id=message_id,
            intent=primary_intent,
            fine_intent=fine_intent,
            intent_confidence=intent_conf,
            reply_text=reply_text,
            template_id=template.id if template else None,
            generation_mode=generation_mode,
            action=action_decision.action,
            allow_auto_send=action_decision.allow_auto_send,
            is_ambiguous=is_ambiguous,
        )

        # 6) 모드 결정 (AUTOPILOT / HITL)
        send_mode = self._auto_reply_mode  # settings 기준
        should_auto_send = (
            send_mode == "AUTOPILOT"
            and action_decision.action == MessageActionType.AUTO_REPLY
            and action_decision.allow_auto_send
        )

        # 7) AutoReply 로그 저장
        self._auto_reply_log_repo.create_from_suggestion(
            suggestion=suggestion,
            message=msg,
            send_mode=send_mode,
            sent=should_auto_send,
        )

        # 8) 스태프 알림 생성 & 저장 (필요 시)
        staff_notification: Optional[StaffNotification] = await self._build_staff_notification(
            message=msg,
            context=context,
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            reply_text=reply_text,
        )

        if staff_notification:
            notif_repo = StaffNotificationRepository(self._db)
            notif_repo.create_from_domain(staff_notification, message_id=msg.id)

        return suggestion

    async def suggest_reply_for_conversation(
        self,
        *,
        thread_id: str,
        ota: Optional[str] = None,
        locale: str = "ko",
        property_code: Optional[str] = None,
        use_llm: bool = True,
        max_messages: int = 20,
    ) -> Optional[AutoReplySuggestion]:
        msgs = (
            self._db.execute(
                select(IncomingMessage)
                .where(IncomingMessage.thread_id == thread_id)
                .order_by(desc(IncomingMessage.received_at), desc(IncomingMessage.id))
            )
            .scalars()
            .all()
        )
        if not msgs:
            return None

        last_guest = None
        for m in msgs:
            direction = getattr(m.direction, "value", None) or str(getattr(m, "direction", "incoming"))
            direction = direction.split(".")[-1]
            if direction == "incoming":
                last_guest = m
                break
        if not last_guest:
            return None

        # ✅ 기존 message 단위 로직과 동일하게 intent 확보 (분류기 직접 호출 금지)
        primary_intent, fine_intent, intent_conf, is_ambiguous = self._ensure_intent(
            msg_id=last_guest.id,
            ota=ota or last_guest.ota,
        )

        if primary_intent == MessageIntent.OTHER and not (last_guest.pure_guest_message or "").strip():
            return None

        context = self._context_builder.build_for_conversation(
            thread_id=thread_id,
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            locale=locale,
            explicit_property_code=property_code,
            max_messages=max_messages,
        )

        channel = (ota or last_guest.ota or "unknown") or "unknown"

        template = self._template_repo.get_best_template_for_intent(
            intent=primary_intent,
            fine_intent=fine_intent,
            locale=locale,
            channel=channel,
            property_code=context.property_code,
            intent_confidence=float(intent_conf or 0.0),
        )

        generation_mode = "template"
        if template and template.body:
            reply_text = template.body
            if use_llm:
                reply_text = await self._generate_with_llm_and_template(
                    context=context,
                    template_body=template.body,
                    locale=locale,
                )
                generation_mode = "llm_with_template"
        else:
            if use_llm:
                reply_text = await self._generate_with_llm_without_template(
                    context=context,
                    locale=locale,
                    guest_message = context.pure_guest_message
                )
                generation_mode = "llm_no_template"
            else:
                reply_text = self._default_fallback_reply(
                    locale=locale,
                    primary_intent=primary_intent,
                )
                generation_mode = "no_template_fallback"

        action_decision = self._action_decider.decide(
            primary_intent=primary_intent,
            fine_intent=fine_intent,
            intent_confidence=float(intent_conf or 0.0),
            is_ambiguous=is_ambiguous,
        )

        suggestion = AutoReplySuggestion(
            message_id=last_guest.id,
            intent=primary_intent,
            fine_intent=fine_intent,
            intent_confidence=float(intent_conf or 0.0),
            reply_text=reply_text,
            template_id=getattr(template, "id", None) if template else None,
            generation_mode=generation_mode,
            action=action_decision.action,
            allow_auto_send=action_decision.allow_auto_send,
            is_ambiguous=is_ambiguous,
        )

        self._auto_reply_log_repo.create_from_suggestion(
            suggestion=suggestion,
            message=last_guest,
            send_mode="PREVIEW",
            sent=False,
        )

        # ⚠️ _ensure_intent 경로는 fine_confidence/reasons를 주지 않으므로 보수적으로 기록
        if fine_intent is not None:
            self._intent_label_repo.create_label(
                message_id=last_guest.id,
                fine_intent=fine_intent,
                confidence=float(intent_conf or 0.0),
                reasons=None,
            )

        return suggestion

    def suggest_reply_for_message_sync(
        self,
        message_id: int,
        ota: str,
        locale: str = "ko",
        property_code: str | None = None,
        use_llm: bool = True,
    ) -> Optional[AutoReplySuggestion]:
        """
        sync 컨텍스트(예: GmailOutboxService 등)에서 사용하기 위한 래퍼.
        내부적으로 asyncio.run 으로 async 메서드를 호출한다.
        """
        return asyncio.run(
            self.suggest_reply_for_message(
                message_id=message_id,
                ota=ota,
                locale=locale,
                property_code=property_code,
                use_llm=use_llm,
            )
        )

    # ------------------------------------------------------------------
    # 내부: Intent 확보 (DB에 없으면 AirbnbIntentClassifier로 분류)
    # ------------------------------------------------------------------

    def _ensure_intent(
        self,
        *,
        msg_id: int,
        ota: Optional[str],
    ) -> Tuple[MessageIntent, Optional[FineGrainedIntent], float, bool]:
        """
        AutoReply에서 사용할 Intent를 보장한다.

        - Airbnb + 게스트 + NEEDS_REPLY + pure_guest_message 가 있는 경우:
            → AirbnbIntentClassifier(LLM)로 재분류하고,
              그 결과를 incoming_messages 에 업데이트.
        - 그 외 OTA / 메시지는 DB에 저장된 intent를 그대로 사용.
        """

        msg = self._msg_repo.get(msg_id)
        if not msg:
            return MessageIntent.OTHER, None, 0.0, True

        # 기본값: DB에 이미 있는 값
        primary_intent: MessageIntent = msg.intent or MessageIntent.OTHER
        intent_conf: float = msg.intent_confidence or 0.0
        fine_intent: Optional[FineGrainedIntent] = msg.fine_intent or None
        is_ambiguous: bool = False

        is_airbnb = (ota == "airbnb") or (msg.ota == "airbnb")
        has_guest_text = bool((msg.pure_guest_message or "").strip())

        if (
            is_airbnb
            and has_guest_text
            and msg.sender_actor == MessageActor.GUEST
            and msg.actionability == MessageActionability.NEEDS_REPLY
        ):
            # ✅ Airbnb 게스트 메시지는 항상 최신 LLM Intent로 재분류
            hybrid: HybridIntentResult = self._intent_classifier.classify_airbnb_guest_intent(
                pure_guest_message=msg.pure_guest_message,
                subject=msg.subject,
                snippet=None,
            )

            mr = hybrid.message_result
            fr: Optional[FineGrainedIntentResult] = hybrid.fine_result

            primary_intent = mr.intent
            intent_conf = mr.confidence
            is_ambiguous = mr.is_ambiguous

            # fine intent 결과가 있으면 같이 업데이트
            if fr is not None:
                fine_intent = fr.fine_intent

                # DB 필드 업데이트 (예외 안 나게 getattr 사용)
                msg.fine_intent = fr.fine_intent
                msg.fine_intent_confidence = getattr(fr, "confidence", None)

                reasons = getattr(fr, "reasons", None)
                if reasons is None:
                    reasons = getattr(fr, "reason", None)
                msg.fine_intent_reasons = reasons

            # primary intent 도 DB에 반영
            msg.intent = primary_intent
            msg.intent_confidence = intent_conf

            self._db.flush()

        return primary_intent, fine_intent, intent_conf, is_ambiguous
    # ------------------------------------------------------------------
    # 내부: ReplyContext 직렬화 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _context_to_dict(context: ReplyContext) -> Dict[str, Any]:
        """
        ReplyContext를 JSON 직렬화 가능한 dict로 변환.
        - dataclass / Pydantic / dict 모두 대응
        """
        if isinstance(context, dict):
            return context
        if is_dataclass(context):
            return asdict(context)
        if hasattr(context, "model_dump"):
            return context.model_dump()
        if hasattr(context, "dict"):
            return context.dict()
        return {
            k: v for k, v in vars(context).items() if not k.startswith("_")
        }

    # ------------------------------------------------------------------
    # 내부: LLM 기반 답변 생성 (템플릿 + 컨텍스트)
    # ------------------------------------------------------------------

    async def _generate_with_llm_and_template(
        self,
        *,
        guest_message: str,
        template_text: str,
        context: ReplyContext,
        locale: str,
    ) -> str:
        """
        기존 템플릿을 '정책/기준 텍스트'로 삼고,
        LLM이 그걸 참고해 답변을 재구성하도록 하는 모드.
        """

        api_key = settings.LLM_API_KEY
        if not api_key:
            return template_text

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model_name = settings.LLM_MODEL or "gpt-4.1-mini"

        system_prompt = (
            "당신은 숙소 호스트를 대신해 게스트 메시지에 답변하는 한국어 어시스턴트입니다.\n"
            "다음 POLICY_TEXT는 숙소의 정책/안내 문구입니다.\n"
            "- POLICY_TEXT에 적힌 제한 사항, 규칙, 금지 사항은 절대 완화하거나 변경하지 마세요.\n"
            "- POLICY_TEXT의 핵심 내용은 그대로 유지하되, 문장을 자연스럽게 다듬고 인삿말과 마무리 멘트만 추가하세요.\n"
            "- 게스트 질문 내용과 컨텍스트를 참고해 불필요한 정보는 빼도 좋지만, 정책 자체를 바꾸지는 마세요.\n"
        )

        policy_block = template_text.strip()
        ctx_dict = self._context_to_dict(context)
        ctx_text = json.dumps(ctx_dict, ensure_ascii=False, default=str)

        user_content = (
            f"[GUEST_MESSAGE]\n{guest_message}\n\n"
            f"[POLICY_TEXT]\n{policy_block}\n\n"
            f"[CONTEXT_JSON]\n{ctx_text}\n\n"
            "위 정보를 참고하여 게스트에게 보낼 답장을 한국어로 한 번만 작성해 주세요.\n"
            "- POLICY_TEXT의 정책/제한 사항은 그대로 유지하세요.\n"
            "- 존댓말을 사용하고, 3~6문장 내로 정리해 주세요.\n"
        )

        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            reply_text = (resp.choices[0].message.content or "").strip()
            return reply_text or template_text
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "LLM_AUTOREPLY(template): failed, fallback to template. err=%s",
                exc,
            )
            return template_text

    # ------------------------------------------------------------------
    # 내부: LLM 기반 답변 생성 (템플릿 없음, 컨텍스트만)
    # ------------------------------------------------------------------

    async def _generate_with_llm_without_template(
        self,
        *,
        guest_message: str,
        context: ReplyContext,
        locale: str,
    ) -> str:
        """
        템플릿이 없는 경우, ReplyContext만으로 LLM이 답변을 생성.
        - 정책/가격/약속은 컨텍스트에 있는 정보만 사용하도록 제한.
        """

        api_key = settings.LLM_API_KEY
        if not api_key:
            return self._default_fallback_reply(
                locale=locale,
                primary_intent=context.primary_intent,
            )

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model_name = settings.LLM_MODEL or "gpt-4.1-mini"

        system_prompt = (
            "You are a professional guest communication assistant for TONO OPERATION, "
            "a hospitality operation company in Korea.\n"
            "You MUST:\n"
            "  - Answer in polite, clear Korean suitable for guests.\n"
            "  - Use ONLY the information provided in the property_profile and context.\n"
            "  - Never invent policies, prices, or promises not present in the context.\n"
            "  - If information is missing, say you will check with the team instead of making it up.\n"
        )

        ctx_dict = self._context_to_dict(context)
        ctx_text = json.dumps(ctx_dict, ensure_ascii=False, default=str)

        user_content = (
            f"[GUEST_MESSAGE]\n{guest_message}\n\n"
            f"[CONTEXT_JSON]\n{ctx_text}\n\n"
            "위 정보를 참고하여 게스트에게 보낼 답장을 한국어로 한 번만 작성해 주세요.\n"
            "- 컨텍스트에 없는 정책/가격/약속은 만들지 마세요.\n"
            "- 정보가 부족하면 확인 후 다시 안내드리겠다고 답변해 주세요.\n"
        )

        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            reply_text = (resp.choices[0].message.content or "").strip()
            if reply_text:
                return reply_text
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "LLM_AUTOREPLY(no_template): failed, fallback to default. err=%s",
                exc,
            )

        return self._default_fallback_reply(
            locale=locale,
            primary_intent=context.primary_intent,
        )

    # ------------------------------------------------------------------
    #  LLM 기반 follow-up 추출
    # ------------------------------------------------------------------

    async def _extract_follow_up_actions_with_llm(
        self,
        *,
        message_text: str,
        primary_intent: MessageIntent,
        fine_intent: Optional[FineGrainedIntent],
        reply_text: str,
        context: ReplyContext,
    ) -> list[str]:
        """
        LLM을 사용해서 스태프가 해야 할 follow-up 작업 리스트를 추출한다.
        """

        api_key = settings.LLM_API_KEY
        if not api_key:
            return self._rule_based_follow_up_actions(
                message_text=message_text,
                primary_intent=primary_intent,
                fine_intent=fine_intent,
            )

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model_name = settings.LLM_MODEL or "gpt-4.1-mini"

        ctx_dict = self._context_to_dict(context)
        ctx_text = json.dumps(ctx_dict, ensure_ascii=False, default=str)

        system_prompt = (
            "당신은 숙소 운영팀(백오피스) 전용 어시스턴트입니다.\n"
            "게스트 메시지와 호스트가 보낸 답장을 보고, 운영팀이 후속으로 처리해야 할 업무 목록을 추출해 주세요.\n"
            "반드시 한국어로 된 짧은 작업 설명 리스트를 JSON 배열 형식으로만 출력해야 합니다.\n"
            "예: [\"자쿠지 비용 입금 확인\", \"냉장고 내 음료 제공 여부 확인\"]\n"
            "- 게스트에게 답장하는 문장은 절대 출력하지 마세요.\n"
            "- 사람이 실제로 해야 할 \"실무 업무\"만 담으세요.\n"
            "- 아무 할 일이 없다면 빈 배열 []만 출력하세요.\n"
        )

        user_content = (
            f"[PRIMARY_INTENT] {primary_intent.name}\n"
            f"[FINE_INTENT] {fine_intent.name if fine_intent else 'NONE'}\n\n"
            f"[GUEST_MESSAGE]\n{message_text}\n\n"
            f"[GUEST_REPLY_TEXT]\n{reply_text}\n\n"
            f"[CONTEXT_JSON]\n{ctx_text}\n\n"
            "위 정보를 바탕으로 운영팀이 후속으로 처리해야 할 업무(Task)를 JSON 배열 형식으로만 출력해 주세요.\n"
            "예외 없이 다음 형식만 허용됩니다:\n"
            "[\"첫 번째 작업\", \"두 번째 작업\"]\n"
        )

        raw = ""
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()

            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("no json array in llm output")

            json_str = raw[start : end + 1]
            tasks = json.loads(json_str)

            tasks = [str(t).strip() for t in tasks if str(t).strip()]
            if tasks:
                return tasks

        except Exception as exc:  # pragma: no cover
            logger.warning(
                "LLM_STAFF_FOLLOWUP: failed or invalid JSON. raw=%r err=%s",
                raw,
                exc,
            )

        return self._rule_based_follow_up_actions(
            message_text=message_text,
            primary_intent=primary_intent,
            fine_intent=fine_intent,
        )

    #------------------------------------------------------------------
    # LLM 실패시 follow-up action 감지
    #------------------------------------------------------------------

    def _rule_based_follow_up_actions(
        self,
        *,
        message_text: str,
        primary_intent: MessageIntent,
        fine_intent: Optional[FineGrainedIntent],
    ) -> list[str]:
        """
        LLM이 실패했을 때만 사용하는 아주 얇은 백업용 규칙.
        """
        text = (message_text or "").strip()
        actions: list[str] = []

        if not text:
            return actions

        if any(k in text for k in ["이체", "입금", "송금", "결제"]):
            actions.append("결제/입금 내역 확인")

        if any(k in text for k in ["충전기", "케이블", "충전"]):
            actions.append("휴대폰 충전기/케이블 비치 여부 확인")

        if any(k in text for k in ["냉장고", "음료", "맥주", "술", "드링크"]):
            actions.append("냉장고 내 음료 및 주류 제공 여부 확인")

        if any(k in text for k in ["체크인", "입실", "체크아웃", "퇴실"]):
            actions.append("체크인/체크아웃 시간 및 가능 여부 확인")

        if "반려" in text or "애견" in text or "강아지" in text or "고양이" in text:
            actions.append("반려동물 동반 가능 여부 및 요금 확인")

        if any(k in text for k in ["불편", "문제", "고장", "안돼", "안 돼", "새는", "냄새"]):
            actions.append("현장 시설/장비 상태 확인 및 조치 필요 여부 확인")

        return list(dict.fromkeys(actions))

    # ------------------------------------------------------------------
    # 내부: 기본 Fallback 문구
    # ------------------------------------------------------------------

    def _default_fallback_reply(
        self,
        *,
        locale: str,
        primary_intent: MessageIntent,
    ) -> str:
        """
        템플릿도 없고, LLM도 안 쓴 경우에 사용할 아주 기본적인 문구.
        """

        if locale.startswith("ko"):
            if primary_intent == MessageIntent.CHECKIN_QUESTION:
                return (
                    "안녕하세요, 문의 주셔서 감사합니다. 체크인 가능 시간과 입실 방법을 확인하여 다시 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.CHECKOUT_QUESTION:
                return (
                    "안녕하세요, 체크아웃 시간 관련 문의 감사드립니다. 현재 예약 정보와 운영 상황을 확인하여 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.LOCATION_QUESTION:
                return (
                    "안녕하세요, 숙소 위치 및 주차 관련 문의 감사드립니다. 정확한 위치와 주차 가능 여부를 확인하여 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.AMENITY_QUESTION:
                return (
                    "안녕하세요, 객실 내 편의시설 관련 문의 감사드립니다. 이용 가능 여부를 확인하여 다시 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.PET_POLICY_QUESTION:
                return (
                    "안녕하세요, 반려동물 동반 관련 문의 감사드립니다. 해당 숙소의 반려동물 정책을 확인하여 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.HOUSE_RULE_QUESTION:
                return (
                    "안녕하세요, 숙소 이용 규칙 관련 문의 감사드립니다. 하우스 룰을 확인하여 다시 자세히 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.RESERVATION_CHANGE:
                return (
                    "안녕하세요, 예약 변경 관련 문의 감사드립니다. 현재 예약 정보와 가능 여부를 확인하여 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.CANCELLATION:
                return (
                    "안녕하세요, 예약 취소 관련 문의 감사드립니다. 취소 및 환불 규정을 확인하여 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.COMPLAINT:
                return (
                    "불편을 드려 정말 죄송합니다. 말씀해 주신 내용은 바로 확인하여 가능한 조치를 안내드리겠습니다."
                )
            if primary_intent == MessageIntent.THANKS_OR_GOOD_REVIEW:
                return (
                    "따뜻한 말씀 감사합니다. 편안한 시간 보내실 수 있도록 끝까지 잘 도와드리겠습니다."
                )
            if primary_intent == MessageIntent.GENERAL_QUESTION:
                return (
                    "안녕하세요, 게스트님,문의 주셔서 감사드리며, 내용을 확인한 뒤 빠르게 안내드리겠습니다."
                )

            return (
                "안녕하세요, 게스트님,문의 주셔서 감사드리며, 내용을 확인한 뒤 빠르게 안내드리겠습니다."
            )

        return "Thank you for your message. We will review your request and get back to you as soon as possible."
