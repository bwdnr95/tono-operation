// src/api/messages.ts
import { apiGet, apiPost } from "./client";
import type {
  MessageListItemDTO,
  MessageDetailDTO,
  MessageWithAutoReply,
  MessageAutoReplyRequest,
  MessageAutoReplySuggestionResponse,
  MessageAutoReplySendRequest,
  MessageAutoReplySendResponse,
} from "../types/messages";

// 쿼리 파라미터 타입
export interface FetchMessagesParams extends Record<string, unknown> {
  limit?: number;
  offset?: number;
  sender_actor?: string;     // "GUEST" | "HOST" | "SYSTEM" 등
  actionability?: string;    // "NEEDS_REPLY" | ...
  intent?: string;
  property_code?: string;
  ota?: string;              // 예: "airbnb"
  include_system?: boolean;  // 기본 false
}

/**
 * 인박스 메시지 리스트 조회
 * GET /api/v1/messages
 *
 * include_system=false (기본)일 때:
 *  - sender_actor = GUEST
 *  - actionability = NEEDS_REPLY
 * 만 자동 적용됨.
 */
export async function fetchInboxMessages(
  params: FetchMessagesParams = {},
): Promise<MessageWithAutoReply[]> {
  const items = await apiGet<MessageListItemDTO[]>("/messages", params);

  const withAuto: MessageWithAutoReply[] = items.map((it) => ({
    ...it,
    auto_reply: null,
  }));

  return withAuto;
}

/**
 * 메시지 상세 조회
 * GET /api/v1/messages/{id}
 */
export async function fetchMessageDetail(
  messageId: number,
): Promise<MessageDetailDTO> {
  return apiGet<MessageDetailDTO>(`/messages/${messageId}`);
}

/**
 * 단건 메시지 자동응답 제안
 * POST /api/v1/messages/{message_id}/auto-reply
 */
export async function requestMessageAutoReplySuggestion(
  messageId: number,
  payload: Partial<MessageAutoReplyRequest> = {},
): Promise<MessageAutoReplySuggestionResponse> {
  const body: MessageAutoReplyRequest = {
    ota: payload.ota ?? null,
    locale: payload.locale ?? "ko",
    property_code: payload.property_code ?? null,
    use_llm: payload.use_llm ?? true,
  };

  return apiPost<MessageAutoReplySuggestionResponse, MessageAutoReplyRequest>(
    `/messages/${messageId}/auto-reply`,
    body,
  );
}

/**
 * 단건 메시지 자동응답 실제 발송
 * POST /api/v1/messages/{message_id}/auto-reply/send
 */
export async function sendMessageAutoReply(
  messageId: number,
  payload: MessageAutoReplySendRequest,
): Promise<MessageAutoReplySendResponse> {
  const body: MessageAutoReplySendRequest = {
    final_reply_text: payload.final_reply_text,
    force: true,
  };

  return apiPost<MessageAutoReplySendResponse, MessageAutoReplySendRequest>(
    `/messages/${messageId}/auto-reply/send`,
    body,
  );
}
