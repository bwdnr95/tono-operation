from dataclasses import dataclass
from typing import List, Optional


@dataclass(slots=True)
class StaffNotification:
    property_code: Optional[str]
    ota: Optional[str]
    guest_name: Optional[str]
    checkin_date: Optional[str]
    checkout_date: Optional[str]        # ← 추가됨!!!
    message_summary: str
    follow_up_actions: List[str]
    status: str = "OPEN"
