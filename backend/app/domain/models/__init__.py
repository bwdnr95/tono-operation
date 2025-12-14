# backend/app/domain/models/__init__.py

from app.db.base import Base

from .email_message import EmailMessage
from .google_token import GoogleToken
from .incoming_message import IncomingMessage
from .message_intent_label import MessageIntentLabel
from .auto_reply_template import AutoReplyTemplate
from .auto_reply_recommendation import AutoReplyRecommendation
from .staff_notification_record import StaffNotificationRecord
from .staff_notification import StaffNotification

# v1.3 THREAD-BASED Conversation models
from .conversation import Conversation, DraftReply, SendActionLog, BulkSendJob

__all__ = [
    "Base",
    "EmailMessage",
    "GoogleToken",
    "IncomingMessage",
    "MessageIntentLabel",
    "AutoReplyTemplate",
    "AutoReplyRecommendation",
    "StaffNotificationRecord",
    "StaffNotification",
    "Conversation",
    "DraftReply",
    "SendActionLog",
    "BulkSendJob",
]
