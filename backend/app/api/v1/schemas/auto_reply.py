# backend/app/api/v1/schemas/auto_reply.py

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.domain.intents import MessageIntent
from app.services.auto_reply_service import AutoReplySuggestion


class AutoReplySuggestionResponse(BaseModel):
    """
    GET /api/v1/messages/{message_id}/suggested-reply 응답 모델.
    """

    model_config = ConfigDict(from_attributes=True)

    message_id: int = Field(..., description="추천이 생성된 메시지 ID")
    intent: Optional[MessageIntent] = Field(
        None,
        description="예측된 Intent (없으면 null)",
    )
    intent_confidence: Optional[float] = Field(
        None,
        description="Intent confidence (0.0 ~ 1.0)",
    )
    reply_text: str = Field(
        ...,
        description="자동응답으로 사용할 텍스트",
    )
    template_id: Optional[int] = Field(
        None,
        description="사용된 템플릿 ID (없으면 null)",
    )

    @classmethod
    def from_service(cls, s: AutoReplySuggestion) -> "AutoReplySuggestionResponse":
        """
        서비스 레벨 DTO(AutoReplySuggestion) → API 응답 모델 변환 헬퍼.
        """
        return cls(
            message_id=s.message_id,
            intent=s.intent,
            intent_confidence=s.intent_confidence,
            reply_text=s.reply_text,
            template_id=s.template_id,
        )