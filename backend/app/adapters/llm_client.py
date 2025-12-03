from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import OpenAI, APIError

from app.core.config import settings


@dataclass
class LLMReplyRequest:
    """
    TONO V3 LLM 요청 DTO.

    V3:
      - context: ReplyContext.to_dict() 결과 (지식 기반 응답용)
    V2 호환:
      - context 가 None이면, 템플릿을 자연스럽게 다듬는 모드로 동작
    """

    intent: str
    guest_message: str
    locale: str
    template_body: str | None = None

    # V3: 지식 기반 응답에 사용
    context: dict[str, Any] | None = None

    # V2 호환: 이전 코드에서 넘기던 property_code (지금은 단순 프롬프트용)
    property_code: str | None = None


class LLMClient:
    """
    OpenAI GPT-4.1 / GPT-4.1-mini 클라이언트 래퍼.

    - settings.LLM_API_KEY, settings.LLM_MODEL 사용
    - self.enabled == False 이면 템플릿 또는 fallback 문구 반환
    - 예외 발생 시에도 서비스 다운 없이 fallback
    """

    def __init__(self, api_key: str | None, model: str):
        self.api_key = api_key
        self.model = model
        self._client: OpenAI | None = None

        if api_key:
            self._client = OpenAI(api_key=api_key)

    @property
    def enabled(self) -> bool:
        return self._client is not None and bool(self.model)

    # --- public API ---

    def generate_reply(self, req: LLMReplyRequest) -> str:
        """
        - req.context 가 있으면: 지식 기반 컨텍스트 모드 (V3)
        - req.context 가 없으면: 템플릿 refine 모드 (V2 호환)
        """

        if not self.enabled:
            return self._fallback_reply(req)

        try:
            if req.context is not None:
                return self._generate_with_context(req)
            return self._generate_template_refine(req)
        except APIError:
            return self._fallback_reply(req)
        except Exception:
            return self._fallback_reply(req)

    # --- V3: 컨텍스트 기반 모드 ---

    def _generate_with_context(self, req: LLMReplyRequest) -> str:
        assert self._client is not None

        system_prompt = self._build_system_prompt_with_context(locale=req.locale)
        context_json = json.dumps(req.context, ensure_ascii=False, indent=2)

        template_hint = ""
        if req.template_body:
            template_hint = (
                "\n\n---\n"
                "Below is an optional reply template that you may use as a starting point. "
                "You MAY rewrite it to better fit the guest message, but do NOT contradict "
                "any policies in the JSON context.\n"
                f"TEMPLATE:\n{req.template_body}"
            )

        user_content = (
            f"# Guest Message\n"
            f"{req.guest_message}\n\n"
            f"# Intent\n"
            f"{req.intent}\n\n"
            f"# Context JSON\n"
            f"{context_json}"
            f"{template_hint}"
        )

        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=800,
        )

        msg = completion.choices[0].message.content or ""
        return msg.strip()

    # --- V2 호환: 템플릿 refine 모드 ---

    def _generate_template_refine(self, req: LLMReplyRequest) -> str:
        """
        컨텍스트 없이 템플릿을 자연스럽게 다듬는 모드.
        property_code 는 단순 메타 정보 문구로만 사용.
        """
        assert self._client is not None

        system_prompt = self._build_system_prompt_template_refine(locale=req.locale)

        meta = ""
        if req.property_code:
            meta = f"(property_code: {req.property_code})"

        base_template = req.template_body or self._fallback_reply(req)

        user_content = (
            f"# Guest Message {meta}\n"
            f"{req.guest_message}\n\n"
            f"# Draft Reply Template\n"
            f"{base_template}\n\n"
            f"Please rewrite or adjust the draft reply so that it answers the guest"
            f" message clearly and naturally. Keep the original policy meaning."
        )

        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=800,
        )

        msg = completion.choices[0].message.content or ""
        return msg.strip()

    # --- 공통 헬퍼 ---

    def _fallback_reply(self, req: LLMReplyRequest) -> str:
        if req.template_body:
            return req.template_body

        if req.locale.startswith("ko"):
            return (
                "문의 주셔서 감사합니다. 게스트님, "
                "담당자가 곧 직접 확인 후 다시 안내드리겠습니다."
            )
        if req.locale.startswith("en"):
            return (
                "Thank you for your message. Our staff will review your request "
                "and get back to you shortly."
            )
        return (
            "문의 주셔서 감사합니다. 담당자가 곧 확인 후 다시 안내드리겠습니다."
        )

    def _build_system_prompt_with_context(self, locale: str) -> str:
        if locale.startswith("ko"):
            return (
                "당신은 숙박업 전문 고객응대 어시스턴트입니다.\n"
                "아래에서 제공되는 JSON 컨텍스트 안에 있는 정보만 사용해서 답변하세요.\n"
                "- 컨텍스트에 없는 정보는 추측하거나 지어내지 마세요.\n"
                "- 모르는 내용이 있으면 '제공된 정보 안에는 해당 내용이 없습니다. "
                "호스트에게 확인해 드리겠습니다.'처럼 정직하게 답하세요.\n"
                "- 게스트에게는 존댓말을 사용하고, 친절하지만 과도하게 가볍지 않은 톤으로 답변하세요.\n"
                "- 정책(체크인 시간, 반려동물, 주차, 흡연 등)은 컨텍스트에 있는 문구를 "
                "최대한 유지하되, 자연스럽게 풀어 설명하세요.\n"
                "- 답변은 이메일/메시지 본문으로 바로 사용할 수 있게 완성된 문장만 작성하세요."
            )

        return (
            "You are a hospitality support assistant.\n"
            "You must answer STRICTLY based on the JSON context provided below.\n"
            "- Do NOT invent policies or details that are not present in the context.\n"
            "- If some information is missing, clearly say that it is not available in the context "
            "and that you will check with the host.\n"
            "- Use a polite, warm but professional tone.\n"
            "- Write a final answer that can be sent to the guest as-is."
        )

    def _build_system_prompt_template_refine(self, locale: str) -> str:
        if locale.startswith("ko"):
            return (
                "당신은 숙박업 전문 고객응대 어시스턴트입니다.\n"
                "아래 제공된 초안 템플릿을 기반으로 게스트 메시지에 맞게 자연스럽게 다듬어 주세요.\n"
                "- 정책의 의미는 바꾸지 말고, 문장을 더 이해하기 쉽게 조정하세요.\n"
                "- 존댓말, 친절하지만 지나치게 가볍지 않은 톤을 유지하세요."
            )

        return (
            "You are a hospitality support assistant.\n"
            "Based on the draft reply template and the guest message, "
            "rewrite the reply so that it is clear, polite and professional.\n"
            "Keep the original policy meaning."
        )


@lru_cache()
def get_llm_client() -> LLMClient:
    api_key = getattr(settings, "LLM_API_KEY", None)
    model = getattr(settings, "LLM_MODEL", "gpt-4.1-mini")
    return LLMClient(api_key=api_key, model=model)
