// src/api/types.ts

// --- Message / Intent DTOs (from backend /messages) ---

export interface MessageListItemDTO {
  id: number;
  gmail_message_id: string;
  thread_id: string;

  subject: string | null;
  from_email: string | null;
  received_at: string; // ISO datetime string

  sender_actor: string;          // MessageActor enum → string 직렬화
  actionability: string;         // MessageActionability enum → string 직렬화

  intent: string | null;         // MessageIntent enum → string 직렬화
  intent_confidence: number | null;

  ota: string | null;
  ota_listing_id: string | null;
  ota_listing_name: string | null;

  property_code: string | null;
}

export interface MessageIntentLabelDTO {
  id: number;
  intent: string;      // MessageIntent
  source: string;      // label source (system/human 등)
  created_at: string;  // ISO datetime
}

export interface MessageDetailDTO {
  id: number;
  gmail_message_id: string;
  thread_id: string;

  subject: string | null;
  from_email: string | null;
  received_at: string;

  sender_actor: string;
  actionability: string;

  intent: string | null;
  intent_confidence: number | null;

  ota: string | null;
  ota_listing_id: string | null;
  ota_listing_name: string | null;

  property_code: string | null;

  text_body: string | null;
  html_body: string | null;
  pure_guest_message: string | null;

  labels: MessageIntentLabelDTO[];
}

// --- AutoReply 로그 DTO (from backend /auto-replies/recent) ---

export interface AutoReplyLogDTO {
  id: number;
  message_id: number;
  property_code: string | null;
  ota: string | null;
  subject: string | null;
  pure_guest_message: string | null;

  intent: string;
  fine_intent: string | null;
  intent_confidence: number;

  reply_text: string;
  generation_mode: string;
  template_id: number | null;

  send_mode: string;      // AUTOPILOT / HITL
  sent: boolean;
  created_at: string;     // ISO datetime

  // ✅ DB 스키마에 있는 failure_reason 컬럼 반영
  failure_reason?: string | null;
}

// --- 인박스용 조합 타입 ---

// MessageListItem + (선택적으로) 최신 AutoReplyLog 1개
export interface MessageWithAutoReply extends MessageListItemDTO {
  [x: string]:
  // --- Message / Intent DTOs (from backend /messages) ---
  any // --- Message / Intent DTOs (from backend /messages) ---
  ;
  auto_reply: AutoReplyLogDTO | null;
}


export interface StaffNotificationDTO {
  id: number;
  message_id: number;

  property_code: string | null;
  ota: string | null;
  guest_name: string | null;

  checkin_date: string | null;
  checkout_date: string | null;

  message_summary: string;
  follow_up_actions: string[];

  status: "OPEN" | "IN_PROGRESS" | "RESOLVED";

  created_at: string;   // ISO datetime
  resolved_at: string | null;
}