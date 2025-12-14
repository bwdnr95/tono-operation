# backend/app/domain/intents/__init__.py

from .types import (
    MessageIntent,
    MessageIntentResult,
    IntentLabelSource,
    FineGrainedIntent,
    FineGrainedIntentResult,
    map_fine_to_primary_intent,
)
from .message_origin import (
    MessageActor,
    MessageActionability,
    AirbnbMessageOriginResult,
)

__all__ = [
    # 1차 Intent / 라벨 소스
    "MessageIntent",
    "MessageIntentResult",
    "IntentLabelSource",

    # 세분화 Intent
    "FineGrainedIntent",
    "FineGrainedIntentResult",
    "map_fine_to_primary_intent",

    # 메세지 Origin
    "MessageActor",
    "MessageActionability",
    "AirbnbMessageOriginResult",
]
