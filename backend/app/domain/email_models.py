from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.domain.intents import MessageIntent


@dataclass
class RawEmail:
    gmail_message_id: str
    gmail_thread_id: Optional[str]
    from_addr: str
    subject: str
    text_body: Optional[str]
    html_body: Optional[str]
    received_at: datetime
    raw_json: dict
    source: str  # 예: "airbnb-gmail"


@dataclass
class AirbnbMessage:
    guest_name: Optional[str]
    listing_name: Optional[str]
    reservation_code: Optional[str]
    airbnb_thread_id: Optional[str]
    intent: MessageIntent
    plain_text: str
    received_at: datetime