// src/api/conversations.ts
import { apiGet, apiPost, apiPatch } from "./client";
import type {
  ConversationDetailDTO,
  ConversationListItemDTO,
  BulkSendEligibleResponseDTO,
  BulkSendPreviewResponseDTO,
  BulkSendSendResponseDTO,
  DraftReplyDTO,
  SendPreviewDTO,
  SendResponseDTO,
} from "../types/conversations";

/**
 * GET /v1/conversations
 * - channel is fixed gmail (backend)
 * - thread_id 기준 필터/정렬
 */
export interface GetConversationsQuery extends Record<string, unknown> {
  // channel fixed by backend, but allow explicit for safety
  channel?: "gmail";
  thread_id?: string | null;
  status?: "open" | "needs_review" | "ready_to_send" | "sent" | "blocked" | null;
  safety_status?: "pass" | "review" | "block" | null;
  updated_since?: string | null; // ISO8601
  limit?: number;
  cursor?: string | null;
}

export interface GetConversationsResponse {
  items: ConversationListItemDTO[];
  next_cursor: string | null;
}

export async function getConversations(
  query: GetConversationsQuery,
): Promise<GetConversationsResponse> {
  return apiGet<GetConversationsResponse>("/conversations", {
    channel: "gmail",
    thread_id: query.thread_id ?? null,
    status: query.status ?? null,
    safety_status: query.safety_status ?? null,
    updated_since: query.updated_since ?? null,
    limit: query.limit ?? 50,
    cursor: query.cursor ?? null,
  });
}

/**
 * GET /v1/conversations/{conversation_id}
 */
export async function getConversationDetail(
  conversationId: string,
): Promise<ConversationDetailDTO> {
  return apiGet<ConversationDetailDTO>(`/conversations/${conversationId}`);
}

/**
 * POST /v1/conversations/{conversation_id}/draft-reply:generate
 * - thread 전체 메시지 컨텍스트 기반
 */
export interface GenerateDraftBody {
  generation_mode: "llm";
}
export interface GenerateDraftResponse {
  draft_reply: DraftReplyDTO;
}

export async function generateDraftReply(
  conversationId: string,
): Promise<GenerateDraftResponse> {
  return apiPost<GenerateDraftResponse, GenerateDraftBody>(
    `/conversations/${conversationId}/draft-reply:generate`,
    { generation_mode: "llm" },
  );
}

/**
 * PATCH /v1/conversations/{conversation_id}/draft-reply
 */
export interface PatchDraftBody {
  content: string;
}
export interface PatchDraftResponse {
  draft_reply: DraftReplyDTO;
}

export async function patchDraftReply(
  conversationId: string,
  content: string,
): Promise<PatchDraftResponse> {
  return apiPatch<PatchDraftResponse, PatchDraftBody>(
    `/conversations/${conversationId}/draft-reply`,
    { content },
  );
}

/**
 * POST /v1/conversations/{conversation_id}/send:preview
 * - confirm_token gate
 */
export async function previewSend(
  conversationId: string,
): Promise<SendPreviewDTO> {
  return apiPost<SendPreviewDTO, Record<string, never>>(
    `/conversations/${conversationId}/send:preview`,
    {},
  );
}

/**
 * POST /v1/conversations/{conversation_id}/send
 * - must include draft_reply_id + confirm_token
 */
export interface SendBody {
  draft_reply_id: string;
  confirm_token: string;
}
export async function sendConversation(
  conversationId: string,
  body: SendBody,
): Promise<SendResponseDTO> {
  return apiPost<SendResponseDTO, SendBody>(`/conversations/${conversationId}/send`, body);
}

/* ===================== Bulk Send ===================== */

/**
 * GET /v1/bulk-send/eligible-conversations
 * - Only returns status=ready_to_send AND safety_status=pass
 * - Must NOT include drafts 없는 Conversation
 */
export interface GetBulkEligibleQuery extends Record<string, unknown> {
  channel?: "gmail";
  updated_since?: string | null;
}
export async function getBulkEligibleConversations(
  query: GetBulkEligibleQuery = {},
): Promise<BulkSendEligibleResponseDTO> {
  return apiGet<BulkSendEligibleResponseDTO>("/bulk-send/eligible-conversations", {
    channel: "gmail",
    updated_since: query.updated_since ?? null,
  });
}

/**
 * POST /v1/bulk-send/preview
 */
export interface BulkPreviewBody {
  conversation_ids: string[]; // 1+
}
export async function bulkPreview(
  body: BulkPreviewBody,
): Promise<BulkSendPreviewResponseDTO> {
  return apiPost<BulkSendPreviewResponseDTO, BulkPreviewBody>("/bulk-send/preview", body);
}

/**
 * POST /v1/bulk-send/{job_id}/send
 */
export interface BulkSendBody {
  confirm_token: string;
}
export async function bulkSend(
  jobId: string,
  body: BulkSendBody,
): Promise<BulkSendSendResponseDTO> {
  return apiPost<BulkSendSendResponseDTO, BulkSendBody>(`/bulk-send/${jobId}/send`, body);
}
