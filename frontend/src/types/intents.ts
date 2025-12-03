// src/types/intents.ts

export type MessageActor = "guest" | "host" | "system" | "unknown";

export type MessageActionability = "needs_reply" | "informational" | "unknown";

export type MessageIntent =
  | "CHECKIN_QUESTION"
  | "CHECKOUT_QUESTION"
  | "RESERVATION_CHANGE"
  | "CANCELLATION"
  | "COMPLAINT"
  | "LOCATION_QUESTION"
  | "AMENITY_QUESTION"
  | "PET_POLICY_QUESTION"
  | "GENERAL_QUESTION"
  | "THANKS_OR_GOOD_REVIEW"
  | "OTHER";

export interface MessageListItem {
  id: number;
  subject: string | null;
  from_email: string | null;
  received_at: string;
  sender_actor: MessageActor;
  actionability: MessageActionability;
  intent: MessageIntent | null;
  intent_confidence: number | null;
  preview_text: string;
}

export interface MessageIntentLabel {
  id: number;
  intent: MessageIntent;
  source: string;
  created_at: string;
}

export interface MessageDetail {
  id: number;
  subject: string | null;
  from_email: string | null;
  received_at: string;
  sender_actor: MessageActor;
  actionability: MessageActionability;
  intent: MessageIntent | null;
  intent_confidence: number | null;
  text_body: string | null;
  pure_guest_message: string | null;
  html_body: string | null;
  labels: MessageIntentLabel[];
}

export interface SuggestedReply {
  message_id: number;
  intent: MessageIntent;
  intent_confidence: number;
  template_id: number | null;
  reply_text: string;
}
