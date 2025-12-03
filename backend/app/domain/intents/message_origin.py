from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel


class MessageActor(StrEnum):
    """Airbnb 스레드 상에서 누가 말한 것인지 (주체)."""
    GUEST = "guest"
    HOST = "host"
    SYSTEM = "system"   # Airbnb 시스템 알림, 마케팅 등
    UNKNOWN = "unknown"


class MessageActionability(StrEnum):
    """이 메일에 대해 TONO가 실제 답변/액션을 해야 하는지."""
    NEEDS_REPLY = "needs_reply"          # 게스트 문의 등 → 답장 필요
    OUTGOING_COPY = "outgoing_copy"      # 우리가 보낸 메시지의 사본 → 답장 불필요
    SYSTEM_NOTIFICATION = "system_notification"  # 예약 확정, 취소 등 알림 → 자동응답 X, 내부 로직만
    FYI = "fyi"                          # 단순 참고용
    UNKNOWN = "unknown"


class AirbnbMessageOriginResult(BaseModel):
    """Airbnb 메일에 대한 1차 분류 결과."""

    actor: MessageActor
    actionability: MessageActionability
    confidence: float
    reasons: List[str]

    # 향후 확장을 위한 필드 (지금은 optional 로만)
    raw_role_label: Optional[str] = None  # "호스트" / "게스트" 등 텍스트 라벨