from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.intents import MessageIntent
from app.domain.models.incoming_message import IncomingMessage
from app.repositories.auto_reply_template_repository import AutoReplyTemplateRepository
from app.repositories.messages import IncomingMessageRepository
from app.repositories.property_profile_repository import PropertyProfileRepository
from app.services.airbnb_intent_classifier import classify_airbnb_guest_intent
from app.services.reply_context_builder import ReplyContextBuilder
from app.adapters.llm_client import get_llm_client, LLMReplyRequest


@dataclass
class AutoReplySuggestion:
    """
    서비스 레벨에서 사용하는 자동응답 제안 DTO.
    (Pydantic 모델은 API 층에서 정의)
    """

    message_id: int
    intent: MessageIntent
    intent_confidence: float
    reply_text: str
    template_id: int | None
    # V3: LLM 사용 여부/모드 기록
    # - template: 템플릿만 사용
    # - llm_context: 컨텍스트 기반 LLM 생성
    # - template_fallback: LLM 실패 → 템플릿으로 대체
    # - no_template_fallback: 템플릿도 없어서 기본 문구로 대체
    generation_mode: str  # "template", "llm_context", "template_fallback", "no_template_fallback"


class AutoReplyService:
    """
    IncomingMessage + Intent + PropertyProfile 기반으로
    자동응답 텍스트를 제안하는 서비스.

    V3:
      - Intent → 템플릿 매핑
      - PropertyProfile / IncomingMessage / Intent 로 ReplyContext 생성
      - 컨텍스트 기반 LLM이 최종 답변 생성 (옵션)
      - 템플릿/기본 문구 fallback
    """

    def __init__(self, session: Session):
        self.session = session
        self.message_repo = IncomingMessageRepository(session)
        self.tpl_repo = AutoReplyTemplateRepository(session)
        self.property_repo = PropertyProfileRepository(session)
        self.context_builder = ReplyContextBuilder(self.property_repo)
        self.llm_client = get_llm_client()

    async def suggest_reply_for_message(
        self,
        *,
        message_id: int,
        ota: str | None = None,
        locale: str | None = "ko",
        property_code: str | None = None,
        use_llm: bool = True,
    ) -> Optional[AutoReplySuggestion]:
        """
        주어진 message_id 에 대해 자동응답 후보를 추천.

        V3 플로우:
          1) message_repo.get_by_id(message_id)
          2) Intent 없으면 classify_airbnb_guest_intent 로 재분류
          3) AutoReplyTemplateRepository.get_best_template_for_intent(intent, locale)
          4) ReplyContextBuilder.build_for_message(...) → context_dict
          5) LLMClient.generate_reply(LLMReplyRequest(...)) 호출
          6) 성공/실패에 따라 generation_mode/텍스트 결정

        property_code 우선순위:
          - API 인자로 들어온 property_code
          - 없으면 IncomingMessage.property_code
          - API 인자로 새 property_code가 들어오면 메시지에도 저장해서 이후 호출에 재사용
        """

        # 1) 메시지 조회
        msg: IncomingMessage | None = self.message_repo.get_by_id(message_id)
        if msg is None:
            return None

        # 1-1) effective_property_code 결정
        #  - 인자로 들어온 property_code가 최우선
        #  - 없으면 메시지에 이미 저장된 값 사용
        msg_property_code = getattr(msg, "property_code", None)
        effective_property_code = property_code or msg_property_code

        # 1-2) 인자로 새 property_code가 들어온 경우 메시지에 저장
        if property_code and property_code != msg_property_code:
            msg.property_code = property_code
            self.session.flush()  # 변경 사항 즉시 반영

        # 2) Intent 가져오기 (없으면 재분류)
        intent = msg.intent
        confidence = msg.intent_confidence or 0.0

        if intent is None:
            intent_result = classify_airbnb_guest_intent(
                decoded_text_body=msg.text_body or "",
                subject=msg.subject,
                snippet=None,
            )
            intent = intent_result.intent
            confidence = intent_result.confidence

            msg.intent = intent
            msg.intent_confidence = confidence
            self.session.flush()  # sync Session

        assert intent is not None, "Intent must not be None after classification"

        # 3) 템플릿 조회
        template = self.tpl_repo.get_best_template_for_intent(
            intent=intent,
            locale=locale or "ko",
        )

        # 템플릿이 있으면 그걸 base, 없으면 기본 fallback
        base_reply = (
            template.body_template
            if template
            else self._default_fallback_reply(locale=locale or "ko")
        )

        # 4) 컨텍스트 구성 (effective_property_code 사용)
        context = self.context_builder.build_for_message(
            message=msg,
            intent=intent,
            property_code=effective_property_code,
        )
        context_dict = context.to_dict()

        generation_mode = "template" if template else "no_template_fallback"
        final_reply = base_reply

        # 5) LLM 기반 응답 생성 (옵션)
        if use_llm and self.llm_client.enabled:
            guest_message = msg.pure_guest_message or msg.text_body or ""

            llm_req = LLMReplyRequest(
                intent=intent.name,
                guest_message=guest_message or "",
                template_body=template.body_template if template else None,
                locale=locale or "ko",
                context=context_dict,                     # 컨텍스트 전달
                property_code=effective_property_code,    # 메타/로그용
            )

            try:
                final_reply = self.llm_client.generate_reply(llm_req)
                generation_mode = "llm_context"
            except Exception:
                # LLM 호출 실패 시 템플릿/기본 문구 fallback
                if template:
                    final_reply = template.body_template
                    generation_mode = "template_fallback"
                else:
                    final_reply = self._default_fallback_reply(locale=locale or "ko")
                    generation_mode = "no_template_fallback"
        else:
            # LLM 사용 안 하거나 비활성화된 경우:
            if not template:
                final_reply = self._default_fallback_reply(locale=locale or "ko")
                generation_mode = "no_template_fallback"

        return AutoReplySuggestion(
            message_id=msg.id,
            intent=intent,
            intent_confidence=confidence,
            reply_text=final_reply,
            template_id=template.id if template else None,
            generation_mode=generation_mode,
        )

    # --- 내부 헬퍼 ---

    def _default_fallback_reply(self, *, locale: str) -> str:
        if locale.startswith("ko"):
            return (
                "문의 주셔서 감사합니다. 현재 문의주신 내용 토대로 "
                "담당자가 확인한 뒤 다시 안내드리겠습니다."
            )
        if locale.startswith("en"):
            return (
                "Thank you for your message. We will review your request "
                "and get back to you shortly."
            )
        return (
            "문의 주셔서 감사합니다. 담당자가 확인 후 다시 안내드리겠습니다."
        )
