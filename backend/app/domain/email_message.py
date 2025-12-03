from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .intents import Intent


@dataclass
class IncomingMessage:
    """
    TONO 내부 표준 메시지 도메인 모델.
    외부 포맷은 Adapter에서 이 모델로 변환.
    """

    source: str
    ota_reservation_id: Optional[str]
    guest_name: Optional[str]
    raw_message: str
    room_no: Optional[str] = None
    received_at: datetime = datetime.utcnow()


@dataclass
class ClassificationResult:
    """
    인텐트 분류 + 답변 정책까지 적용된 결과.
    """

    intent: Intent
    confidence: float
    auto_reply: bool
    need_human: bool
    reply_text: str
    sub_intent: Optional[str] = None