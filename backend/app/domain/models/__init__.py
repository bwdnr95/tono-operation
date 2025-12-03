# backend/app/domain/models/__init__.py

from app.db.base import Base  # 선택사항: Base도 여기서 노출할 수 있음

from .email_message import EmailMessage
from .google_token import GoogleToken
from .incoming_message import IncomingMessage
from .message_intent_label import MessageIntentLabel
from .auto_reply_template import AutoReplyTemplate
from .auto_reply_recommendation import AutoReplyRecommendation

__all__ = [
    "Base",
    "EmailMessage",
    "GoogleToken",
    "IncomingMessage",
    "MessageIntentLabel",
    "AutoReplyTemplate",
    "AutoReplyRecommendation",
]
