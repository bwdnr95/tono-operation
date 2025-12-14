// src/types/conversations.ts
// CURRENT Canonical Definition: Conversation = (channel="gmail", thread_id)

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
  thread_id: string; // required, unique within channel
  status: ConversationStatus;
  safety_status: SafetyStatus;
  last_message_id: number | null; // incoming_messages.id
  created_at: string; // ISO8601
  updated_at: string; // ISO8601
}

export interface ConversationDTO extends ConversationListItemDTO {}

export type MessageDirection = "incoming" | "outgoing";

export interface ThreadMessageDTO {
  id: number; // incoming_messages.id (integer)
  thread_id: string;
  direction: MessageDirection;
  content: string;
  created_at: string; // ISO8601
}

export interface DraftReplyDTO {
  id: string; // uuid
  conversation_id: string; // uuid
  thread_id: string; // required
  content: string;
  safety_status: SafetyStatus;
  created_at: string;
  updated_at: string;
}

export type DraftAction = "preview" | "send" | "bulk_send";

export interface SendActionLogDTO {
  id: string; // uuid
  conversation_id: string; // uuid
  thread_id: string; // required
  message_id: number | null; // integer
  action: DraftAction;
  created_at: string; // ISO8601
}

/* ===== Conversation Detail ===== */
export interface ConversationDetailDTO {
  conversation: ConversationDTO;
  messages: ThreadMessageDTO[]; // thread 전체 히스토리
  draft_reply: DraftReplyDTO | null; // thread 귀속 필수
  send_logs: SendActionLogDTO[]; // latest-first (backend)
}

/* ===== Send Preview / Send ===== */
export interface SendPreviewDTO {
  conversation_id: string; // uuid
  thread_id: string; // required
  draft_reply_id: string;
  safety_status: SafetyStatus;
  can_send: boolean;
  preview_content: string;
  confirm_token: string;
}

export interface SendResponseDTO {
  conversation_id: string;
  thread_id: string;
  sent_at: string;
  status: "sent" | "blocked";
}

/* ===== Bulk Send ===== */
export type BulkSendJobStatus = "pending" | "completed" | "partial_failed" | "failed";

export interface BulkSendJobDTO {
  id: string; // uuid
  conversation_ids: string[]; // uuid[]
  status: BulkSendJobStatus;
  created_at: string;
  completed_at: string | null;
}

export interface BulkSendEligibleResponseDTO {
  items: ConversationListItemDTO[]; // always safety_status="pass" & status="ready_to_send"
}

export interface BulkSendPreviewItemDTO {
  conversation_id: string;
  thread_id: string;
  draft_reply_id: string | null; // must exist for sendable
  safety_status: SafetyStatus;
  can_send: boolean;
  preview_content: string | null;
  blocked_reason: string | null;
}

export interface BulkSendPreviewResponseDTO {
  job: BulkSendJobDTO; // status="pending"
  previews: BulkSendPreviewItemDTO[];
  confirm_token: string;
}

export type BulkSendResult = "sent" | "skipped" | "failed";

export interface BulkSendResultItemDTO {
  conversation_id: string;
  thread_id: string;
  result: BulkSendResult;
  error_code: string | null;
  error_message: string | null;
  sent_at: string | null;
}

export interface BulkSendSendResponseDTO {
  job_id: string;
  status: Exclude<BulkSendJobStatus, "pending">;
  results: BulkSendResultItemDTO[];
}
