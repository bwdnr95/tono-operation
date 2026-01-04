from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.config import settings

# OpenAI 클라이언트 import (v1 / v0 양쪽 호환 시도)
try:
    from openai import OpenAI

    _HAS_OPENAI_CLIENT = True
except ImportError:  # fallback to legacy openai
    import openai  # type: ignore

    OpenAI = None  # type: ignore
    _HAS_OPENAI_CLIENT = False

logger = logging.getLogger(__name__)


@dataclass
class LLMReplyRequest:
    """
    AutoReplyService → LLMClient 로 전달되는 요청 DTO.
    """

    intent: str
    guest_message: str
    locale: str
    context: Dict[str, Any]
    template_body: str | None = None
    property_code: str | None = None


class LLMClient:
    """
    OpenAI 기반 LLM 클라이언트.

    - settings.LLM_API_KEY, settings.LLM_MODEL 을 사용
    - self.enabled == False 인 경우 템플릿 또는 기본 문구를 그대로 반환
    - 예외 발생 시에도 서비스 다운 없이 fallback 처리
    """

    def __init__(
        self,
        api_key: str | None,
        model: str | None,
    ) -> None:
        self._api_key = api_key
        self._model = model or "gpt-4.1-mini"

        if not api_key:
            self._client = None
        else:
            if _HAS_OPENAI_CLIENT:
                self._client = OpenAI(api_key=api_key)
            else:
                # legacy openai 설정
                openai.api_key = api_key  # type: ignore
                self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self._api_key and self._model)

    def generate_reply(self, req: LLMReplyRequest) -> str:
        """
        컨텍스트 기반 자동응답 생성.

        원칙:
          - JSON 컨텍스트에 포함된 정보만 사용
          - 모르면 모른다고 말하기
          - 브랜드 톤은 컨텍스트(extra_metadata 등)에 정의된 범위 내에서만 적용
        """

        if not self.enabled:
            logger.info(
                "llm_disabled_fallback intent=%s property_code=%s",
                req.intent,
                req.property_code,
            )
            if req.template_body:
                return req.template_body
            return self._default_fallback_reply(locale=req.locale)

        system_prompt = self._build_system_prompt(req)
        user_prompt = self._build_user_prompt(req)

        # DEBUG: LLM 호출 전 최소 정보만 로그 (context 전체는 AutoReplyService 쪽에서 찍음)
        try:
            logger.debug(
                "llm_request_meta %s",
                json.dumps(
                    {
                        "intent": req.intent,
                        "property_code": req.property_code,
                        "locale": req.locale,
                        "has_template": bool(req.template_body),
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception:
            logger.debug("llm_request_meta_log_failed", exc_info=True)

        try:
            if _HAS_OPENAI_CLIENT and self._client is not None:
                # openai>=1.x 스타일
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
                reply = completion.choices[0].message.content.strip()
            else:
                # legacy openai.ChatCompletion 스타일
                completion = openai.ChatCompletion.create(  # type: ignore
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
                reply = completion["choices"][0]["message"]["content"].strip()  # type: ignore

            logger.debug("llm_reply_generated length=%s", len(reply))
            return reply

        except Exception as e:
            logger.warning(
                "llm_call_failed intent=%s property_code=%s error=%r",
                req.intent,
                req.property_code,
                e,
                exc_info=True,
            )
            if req.template_body:
                return req.template_body
            return self._default_fallback_reply(locale=req.locale)

    # -------------------------------------------------- #

    def _build_system_prompt(self, req: LLMReplyRequest) -> str:
        """
        LLM에게 '이 JSON 컨텍스트에 있는 정보만 사용하라'를 강하게 규정하는 system prompt.
        """

        locale = req.locale or "ko"
        # 언어별 기본 톤은 일단 한국어/영어만 구분
        if locale.startswith("ko"):
            base = (
                "당신은 숙박업소 게스트 문의에 답변하는 고객 응대 어시스턴트입니다. "
                "다음 JSON 컨텍스트에 포함된 정보만 사용해서 답변해야 합니다. "
                "컨텍스트에 없는 정보는 절대 추측하지 말고, AI가 작성한  "
                "'해당 정보는 전달해주신 정보를 담당자가 확인 후 안내드리겠다'고 안내하세요. "
                "친절하고 차분한 톤으로, 너무 길지 않게 핵심 위주로 답변하세요."
            )
        else:
            base = (
                "You are a guest messaging assistant for a lodging operation. "
                "You must answer ONLY using the information contained in the provided JSON context. "
                "If something is not present in the context, explicitly say that the information "
                "is not available in the system instead of guessing. "
                "Use a polite, calm tone and keep the answer concise but helpful."
            )

        return base

    def _build_user_prompt(self, req: LLMReplyRequest) -> str:
        """
        게스트 메시지 + Intent + Context JSON 을 하나의 user prompt 로 구성.
        """
        context_json = json.dumps(req.context, ensure_ascii=False, indent=2)

        if req.locale.startswith("ko"):
            parts = [
                f"[INTENT]: {req.intent}",
                f"[PROPERTY_CODE]: {req.property_code or 'UNKNOWN'}",
                "",
                "[CONTEXT_JSON]:",
                context_json,
                "",
                "[GUEST_MESSAGE]:",
                req.guest_message.strip(),
            ]
            if req.template_body:
                parts.extend(
                    [
                        "",
                        "[TEMPLATE_HINT]:",
                        "아래 템플릿은 참고용 예시입니다. 이 템플릿의 어조와 구조를 참고하되, "
                        "위 CONTEXT_JSON에 맞지 않는 정보는 절대 사용하지 마세요.",
                        req.template_body,
                    ]
                )
        else:
            parts = [
                f"[INTENT]: {req.intent}",
                f"[PROPERTY_CODE]: {req.property_code or 'UNKNOWN'}",
                "",
                "[CONTEXT_JSON]:",
                context_json,
                "",
                "[GUEST_MESSAGE]:",
                req.guest_message.strip(),
            ]
            if req.template_body:
                parts.extend(
                    [
                        "",
                        "[TEMPLATE_HINT]:",
                        "The following template is a hint. Mimic its tone and structure, "
                        "but do NOT include any information that is not present in CONTEXT_JSON.",
                        req.template_body,
                    ]
                )

        return "\n".join(parts)

    # -------------------------------------------------- #

    def _default_fallback_reply(self, *, locale: str) -> str:
        if locale.startswith("ko"):
            return (
                "문의 주셔서 감사합니다. 현재 문의주신 내용을 "
                "담당자가 확인 후 다시 답변드리겠습니다."
            )
        if locale.startswith("en"):
            return (
                "Thank you for your message. Based on the current system information, "
                "a precise answer is difficult, so a staff member will review your request "
                "and get back to you."
            )
        return (
            "문의 주셔서 감사합니다. 담당자가 확인 후 다시 안내드리겠습니다."
        )


# ------------------------------------------------------ #
# 모듈 레벨 싱글톤 헬퍼
# ------------------------------------------------------ #

_llm_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """
    settings 기반 LLMClient 싱글톤 생성.
    """
    global _llm_client_singleton
    if _llm_client_singleton is None:
        api_key = getattr(settings, "LLM_API_KEY", None)
        model = getattr(settings, "LLM_MODEL", None)
        _llm_client_singleton = LLMClient(api_key=api_key, model=model)
    return _llm_client_singleton


# ------------------------------------------------------ #
# OpenAI 클라이언트 싱글톤 (DI용)
# ------------------------------------------------------ #

_openai_client_singleton: "OpenAI | None" = None


def get_openai_client() -> "OpenAI | None":
    """
    OpenAI 클라이언트 싱글톤 생성 (DI용).
    
    사용처:
    - AutoReplyService
    - CommitmentExtractor
    
    Returns:
        OpenAI 클라이언트 인스턴스, API 키 없으면 None
    """
    global _openai_client_singleton
    if _openai_client_singleton is None:
        api_key = getattr(settings, "LLM_API_KEY", None)
        if api_key and _HAS_OPENAI_CLIENT:
            _openai_client_singleton = OpenAI(api_key=api_key)
    return _openai_client_singleton
