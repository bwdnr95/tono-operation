# backend/app/domain/intents/auto_actions.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from app.domain.intents import (
    MessageIntent,
    FineGrainedIntent,
)


class MessageActionType(StrEnum):
    """
    메시지를 보고 TONO가 어떤 액션을 취해야 하는지에 대한 1차 분류.
    """

    AUTO_REPLY = "AUTO_REPLY"  # 바로 게스트에게 자동 답장 보내도 되는 케이스
    DRAFT_ONLY = "DRAFT_ONLY"  # 초안만 만들고, 직원이 확인 후 발송
    STAFF_REVIEW_REQUIRED = "STAFF_REVIEW_REQUIRED"  # 직원 검토 필수 (민감/복잡)
    STAFF_ALERT = "STAFF_ALERT"  # 바로 직원 알림 보내야 하는 케이스(클레임 등)
    NO_ACTION = "NO_ACTION"  # 아무 것도 안 해도 되는 케이스(단순 감사 인사 등)


@dataclass(slots=True)
class MessageActionDecision:
    """
    Intent → Action 매핑 결과 DTO.
    """

    action: MessageActionType
    reason: str
    escalation_level: int = 0  # 0: 일반, 1: 중요, 2: 긴급 등
    allow_auto_send: bool = False  # 이 메시지는 사람 승인 없이 바로 발송해도 되는가?
    block_auto_reply: bool = False  # 자동응답 자체를 막아야 하는가?
    override_locale: Optional[str] = None  # 필요시 locale 강제
