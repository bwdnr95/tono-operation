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
from .reservation_info import ReservationInfo, ReservationStatus
from .alteration_request import AlterationRequest, AlterationStatus
from .ical_blocked_date import IcalBlockedDate
from .notification import Notification, NotificationType
from .push_subscription import PushSubscription
from .complaint import Complaint, ComplaintCategory, ComplaintSeverity, ComplaintStatus
# v1.3 THREAD-BASED Conversation models
from .conversation import Conversation, DraftReply, SendActionLog

# v2.0 Orchestrator models
from .orchestrator import (
    Decision,
    ReasonCode,
    HumanAction,
    AutomationEligibility,
    DecisionLog,
    AutomationPattern,
    PolicyRule,
)


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
    "ReservationInfo",
    "ReservationStatus",
    "AlterationRequest",
    "AlterationStatus",
    "IcalBlockedDate",
    "Conversation",
    "DraftReply",
    "SendActionLog",
    "Notification",
    "NotificationType",
    "PushSubscription",
    "Complaint",
    "ComplaintCategory",
    "ComplaintSeverity",
    "ComplaintStatus",
    "AnswerEmbedding",
    # Orchestrator models
    "Decision",
    "ReasonCode",
    "HumanAction",
    "AutomationEligibility",
    "DecisionLog",
    "AutomationPattern",
    "PolicyRule",
]
