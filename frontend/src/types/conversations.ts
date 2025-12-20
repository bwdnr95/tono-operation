// src/types/conversations.ts
// Canonical: Conversation = (channel="gmail", airbnb_thread_id)

export type Channel = "gmail";

export type ConversationStatus =
  | "open"
  | "needs_review"
  | "ready_to_send"
  | "sent"
  | "blocked";

export type SafetyStatus = "pass" | "review" | "block";

export interface ConversationListItemDTO {
  id: string; // uuid
  channel: Channel; // fixed "gmail"
  airbnb_thread_id: string; // required
  property_code?: string | null; // 숙소 코드
  status: ConversationStatus;
  safety_status: SafetyStatus;
  is_read: boolean; // 읽음/안읽음 상태
  last_message_id: number | null; // incoming_messages.id
  created_at: string; // ISO8601
  updated_at: string; // ISO8601
  // 게스트 정보
  guest_name?: string | null;
  checkin_date?: string | null;
  checkout_date?: string | null;
}

export interface ConversationDTO extends ConversationListItemDTO {}

export type MessageDirection = "incoming" | "outgoing";

export interface ThreadMessageDTO {
  id: number; // incoming_messages.id (integer)
  airbnb_thread_id: string;
  direction: MessageDirection;
  content: string;
  created_at: string; // ISO8601
  guest_name?: string | null;
  checkin_date?: string | null;
  checkout_date?: string | null;
}

import type { OutcomeLabel, HumanOverride } from './outcomeLabel';

export interface DraftReplyDTO {
  id: string; // uuid
  conversation_id: string; // uuid
  airbnb_thread_id: string; // required
  content: string;
  safety_status: SafetyStatus;
  created_at: string;
  updated_at: string;
  // v3: Outcome Label 4축
  outcome_label?: OutcomeLabel | null;
  human_override?: HumanOverride | null;
}

/**
 * MVP: Preview 없음.
 * Send 로그는 "send" / "bulk_send"만 남김.
 */
export type DraftAction = "send" | "bulk_send";

export interface SendActionLogDTO {
  id: string; // uuid
  conversation_id: string; // uuid
  airbnb_thread_id: string;
  message_id: number | null; // outgoing 메시지/로그에 매핑될 수 있으면 사용
  action: DraftAction;
  created_at: string; // ISO8601
}

/* ===== Conversation Detail ===== */
export interface ConversationDetailDTO {
  conversation: ConversationDTO;
  messages: ThreadMessageDTO[]; // thread 전체 히스토리
  draft_reply: DraftReplyDTO | null; // thread 귀속
  send_logs: SendActionLogDTO[]; // latest-first (backend)
}

/* ===== List / Pagination ===== */
export type GetConversationsResponse = {
  items: ConversationListItemDTO[];
  next_cursor: string | null;
};

export type GetConversationsParams = {
  channel: Channel;
  property_code?: string | null; // 숙소 코드 필터
  airbnb_thread_id?: string | null;
  status?: ConversationStatus | null;
  safety_status?: SafetyStatus | null;
  is_read?: boolean | null; // 읽음/안읽음 필터
  updated_since?: string | null;
  limit?: number;
  cursor?: string | null;
};

/* ===== Send ===== */
export interface SendBodyDTO {
  draft_reply_id: string;
}

export interface SendResponseDTO {
  conversation_id: string;
  airbnb_thread_id: string;
  sent_at: string;
  status: "sent" | "blocked";
}

/* ===== Bulk Eligible (MVP: 단순 목록) =====
 * MVP에서는 job/preview/token 없이
 * eligible 목록을 가져와서 bulk-send/send 호출
 */
export interface BulkSendEligibleResponseDTO {
  items: ConversationListItemDTO[];
  next_cursor: string | null;
}

/* ===== Bulk Send ===== */
export interface BulkSendRequestDTO {
  conversation_ids: string[];
}

export interface BulkSendResultItemDTO {
  conversation_id: string;
  result: "sent" | "skipped" | "failed";
  error_message: string | null;
  sent_at: string | null;
}

export interface BulkSendResponseDTO {
  total: number;
  sent: number;
  skipped: number;
  failed: number;
  results: BulkSendResultItemDTO[];
}