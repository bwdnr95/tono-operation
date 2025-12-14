// src/types/messages.ts

// Intent 라벨 DTO (상세에서 사용)
export interface MessageIntentLabelDTO {
  id: number;
  intent: string;      // 예: "CHECKIN_QUESTION"
  source: string;      // "SYSTEM" | "MANUAL" 등
  created_at: string;  // ISO datetime
}

// 메시지 리스트 아이템 DTO
// GET /api/v1/messages
export interface MessageListItemDTO {
  id: number;
  gmail_message_id: string;
  thread_id: string;

  subject: string | null;
  from_email: string | null;
  received_at: string;          // ISO datetime

  sender_actor: string;         // "GUEST" | "HOST" | "SYSTEM" | ...
  actionability: string;        // "NEEDS_REPLY" | ...

  intent: string | null;
  intent_confidence: number | null;

  ota: string | null;
  ota_listing_id: string | null;
  ota_listing_name: string | null;

  property_code: string | null;

  // 리스트에서 미리보기로 쓸 수 있는 필드 (있을 수도, 없을 수도 있음)
  pure_guest_message?: string | null;

  // ✅ 파서가 채운 게스트 / 숙박 메타
  guest_name: string | null;
  checkin_date: string | null;      // "YYYY-MM-DD"
  checkout_date: string | null;     // "YYYY-MM-DD"

  // ✅ 세부 intent / 후속 액션 메타
  fine_intent: string | null;       // 예: "LATE_CHECKIN"
  fine_intent_confidence: number | null;
  suggested_action: string | null;  // 예: "NEED_STAFF_FOLLOWUP"
}

// 메시지 상세 DTO
// GET /api/v1/messages/{id}
export interface MessageDetailDTO extends MessageListItemDTO {
  text_body: string | null;
  html_body: string | null;
  // 상세에서는 항상 pure_guest_message가 내려온다고 가정
  pure_guest_message: string | null;

  // fine-grained intent 설명
  fine_intent_reasons: string | null;
  allow_auto_send: boolean | null;

  labels: MessageIntentLabelDTO[];
}

// AutoReply 로그 DTO는 기존 intents.ts 에 있음
import type { AutoReplyLogDTO } from "./intents";

/**
 * Inbox 리스트에서 사용할 ViewModel:
 * 메시지 + (있다면) 최신 AutoReply 로그
 */
export interface MessageWithAutoReply extends MessageListItemDTO {
  auto_reply: AutoReplyLogDTO | null;
}

/**
 * 단건 메시지 자동응답 제안 요청
 * POST /api/v1/messages/{message_id}/auto-reply
 */
export interface MessageAutoReplyRequest {
  ota?: string | null;
  locale?: string;            // 기본 "ko"
  property_code?: string | null;
  use_llm?: boolean;          // false면 템플릿/룰 기반만
}

/**
 * 단건 메시지 자동응답 제안 응답
 */
export interface MessageAutoReplySuggestionResponse {
  message_id: number;
  intent: string;
  intent_confidence: number | null;
  reply_text: string;
  template_id: number | null;
  generation_mode: string;    // "LLM_WITH_TEMPLATE" 등
}

/**
 * 단건 자동응답 실제 발송 요청
 * POST /api/v1/messages/{message_id}/auto-reply/send
 */
export interface MessageAutoReplySendRequest {
  final_reply_text: string;
  force?: boolean;            // 기본 false
}

/**
 * 단건 자동응답 실제 발송 응답
 */
export interface MessageAutoReplySendResponse {
  message_id: number;
  sent: boolean;
  skip_reason: string | null;
  log_id: number | null;
  sent_at: string | null;
}
