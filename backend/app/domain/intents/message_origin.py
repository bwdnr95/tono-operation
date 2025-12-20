from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel


class MessageActor(StrEnum):
    """Airbnb 스레드 상에서 누가 말한 것인지 (주체)."""
    GUEST = "GUEST"
    HOST = "HOST"
    SYSTEM = "SYSTEM"
    UNKNOWN = "UNKNOWN"


class MessageActionability(StrEnum):
    """이 메일에 대해 TONO가 실제 답변/액션을 해야 하는지."""
    NEEDS_REPLY = "NEEDS_REPLY"
    OUTGOING_COPY = "OUTGOING_COPY"
    SYSTEM_NOTIFICATION = "SYSTEM_NOTIFICATION"
    FYI = "FYI"
    UNKNOWN = "UNKNOWN"


class AirbnbMessageOriginResult(BaseModel):
    """Airbnb 메일에 대한 1차 분류 결과."""

    actor: MessageActor
    actionability: MessageActionability
    confidence: float
    reasons: List[str]

    # 향후 확장을 위한 필드 (지금은 optional 로만)
    raw_role_label: Optional[str] = None  # "호스트" / "게스트" 등 텍스트 라벨