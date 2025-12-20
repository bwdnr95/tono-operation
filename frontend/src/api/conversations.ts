// frontend/src/api/conversations.ts
/**
 * Conversation API
 * - 모든 DTO는 types/conversations.ts에서 import
 * - Preview/Token 없음 (MVP)
 */
import { apiGet, apiPost, apiPatch } from "./client";

import type {
  ConversationDetailDTO,
  GetConversationsParams,
  GetConversationsResponse,
  SendBodyDTO,
  SendResponseDTO,
  BulkSendEligibleResponseDTO,
  BulkSendRequestDTO,
  BulkSendResponseDTO,
} from "../types/conversations";

// ============================================================
// Conversation
// ============================================================

// GET /api/v1/conversations
export async function getConversations(
  params: GetConversationsParams,
): Promise<GetConversationsResponse> {
  return apiGet<GetConversationsResponse>("/conversations", params);
}

// GET /api/v1/conversations/{id}
export async function getConversationDetail(
  conversationId: string,
): Promise<ConversationDetailDTO> {
  return apiGet<ConversationDetailDTO>(`/conversations/${conversationId}`);
}

// ============================================================
// Draft
// ============================================================

// POST /api/v1/conversations/{id}/draft-reply/generate
export async function generateDraftReply(
  conversationId: string,
): Promise<{ draft_reply: ConversationDetailDTO["draft_reply"] }> {
  return apiPost<{ draft_reply: ConversationDetailDTO["draft_reply"] }>(
    `/conversations/${conversationId}/draft-reply/generate`,
    {},
  );
}

// PATCH /api/v1/conversations/{id}/draft-reply
export async function patchDraftReply(
  conversationId: string,
  content: string,
): Promise<{ draft_reply: ConversationDetailDTO["draft_reply"] }> {
  return apiPatch<{ draft_reply: ConversationDetailDTO["draft_reply"] }, { content: string }>(
    `/conversations/${conversationId}/draft-reply`,
    { content },
  );
}

// ============================================================
// Send (단건)
// ============================================================

// POST /api/v1/conversations/{id}/send
export async function sendConversation(
  conversationId: string,
  body: SendBodyDTO,
): Promise<SendResponseDTO> {
  return apiPost<SendResponseDTO, SendBodyDTO>(
    `/conversations/${conversationId}/send`,
    body,
  );
}

// ============================================================
// Bulk Send
// ============================================================

// GET /api/v1/bulk-send/eligible-conversations
export async function getBulkEligibleConversations(params?: {
  limit?: number;
  cursor?: string;
}): Promise<BulkSendEligibleResponseDTO> {
  return apiGet<BulkSendEligibleResponseDTO>(
    "/bulk-send/eligible-conversations",
    params,
  );
}

// POST /api/v1/bulk-send/send
export async function bulkSend(
  conversationIds: string[],
): Promise<BulkSendResponseDTO> {
  return apiPost<BulkSendResponseDTO, BulkSendRequestDTO>(
    "/bulk-send/send",
    { conversation_ids: conversationIds },
  );
}

// ============================================================
// 읽음/안읽음 처리
// ============================================================

export interface MarkReadResponse {
  conversation_id: string;
  is_read: boolean;
}

// POST /api/v1/conversations/{id}/mark-read
export async function markConversationRead(
  conversationId: string,
): Promise<MarkReadResponse> {
  return apiPost<MarkReadResponse>(`/conversations/${conversationId}/mark-read`, {});
}

// POST /api/v1/conversations/{id}/mark-unread
export async function markConversationUnread(
  conversationId: string,
): Promise<MarkReadResponse> {
  return apiPost<MarkReadResponse>(`/conversations/${conversationId}/mark-unread`, {});
}

// ============================================================
// Gmail Ingest (Conversation 기반)
// ============================================================

export interface GmailIngestRequest {
  max_results?: number;
  newer_than_days?: number;
}

export interface GmailIngestConversationItem {
  conversation_id: string;
  thread_id: string;
  status: string;
  draft_content?: string;
  guest_message?: string;
}

export interface GmailIngestResponse {
  total_parsed: number;
  total_conversations: number;
  conversations: GmailIngestConversationItem[];
}

// POST /api/v1/conversations/ingest-gmail
// Gmail 인제스트 + Conversation 생성 + Draft 생성
export async function ingestGmailMessages(
  params?: GmailIngestRequest,
): Promise<GmailIngestResponse> {
  return apiPost<GmailIngestResponse, GmailIngestRequest>(
    "/conversations/ingest-gmail",
    {
      max_results: params?.max_results ?? 50,
      newer_than_days: params?.newer_than_days ?? 3,
    },
  );
}
