import re
from datetime import datetime
from typing import Optional

from backend.app.domain.email_message import IncomingMessage


class AirbnbEmailAdapter:
    """
    이메일 인바운드 웹훅에서 받은 payload를
    TONO의 IncomingMessage로 변환하는 어댑터.

    실제 SES/SendGrid/Gmail API 포맷은 다를 수 있으니,
    이 클래스는 '중간 변환층'으로 유지.
    """

    @staticmethod
    def parse(
        from_addr: str,
        subject: str,
        text_body: str,
        html_body: Optional[str] = None,
        received_at: Optional[datetime] = None,
    ) -> IncomingMessage:
        """
        매우 단순화된 버전.
        - 나중에: 예약번호/게스트 이름을 정규식 + 템플릿별 파서로 정교하게 추출.
        """

        raw_message = text_body or html_body or ""

        # 게스트 이름 추출 (예: "New message from Kim" 같은 패턴)
        guest_name = None
        m = re.search(r"from\s+([A-Za-z가-힣]+)", subject, re.IGNORECASE)
        if m:
            guest_name = m.group(1)

        # 예약번호 패턴 (예: HMQS5HTSWX 같은)
        reservation_id = None
        m2 = re.search(r"\b[0-9A-Z]{8,12}\b", raw_message)
        if m2:
            reservation_id = m2.group(0)

        return IncomingMessage(
            source="airbnb_email",
            ota_reservation_id=reservation_id,
            guest_name=guest_name,
            raw_message=raw_message,
            room_no=None,
            received_at=received_at or datetime.utcnow(),
        )