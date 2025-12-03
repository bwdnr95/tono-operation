from sqlalchemy.orm import Session

from app.domain.email_models import RawEmail, AirbnbMessage
from app.domain.models.email_message import EmailMessage


def get_email_by_gmail_message_id(
    db: Session, gmail_message_id: str
) -> EmailMessage | None:
    return (
        db.query(EmailMessage)
        .filter(EmailMessage.gmail_message_id == gmail_message_id)
        .first()
    )


def create_email_message_from_domain(
    db: Session,
    *,
    raw_email: RawEmail,
    airbnb_message: AirbnbMessage,
) -> EmailMessage:
    obj = EmailMessage(
        gmail_message_id=raw_email.gmail_message_id,
        gmail_thread_id=raw_email.gmail_thread_id,
        from_addr=raw_email.from_addr,
        subject=raw_email.subject,
        text_body=raw_email.text_body,
        html_body=raw_email.html_body,
        raw_json=raw_email.raw_json,
        source=raw_email.source,
        intent=airbnb_message.intent.name,
        received_at=airbnb_message.received_at,
        guest_name=airbnb_message.guest_name,
        listing_name=airbnb_message.listing_name,
        reservation_code=airbnb_message.reservation_code,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj