// src/api/jobs.ts
import { apiPost } from "./client";

/**
 * 공통 Job Request (full 파이프라인 / preview 공통)
 */
export interface GmailAirbnbAutoReplyJobRequest {
  max_results: number;
  newer_than_days: number;
  extra_query: string | null;
  query: string | null;
  force: boolean;
}

/**
 * 전체 파이프라인 (발송 포함) Job 응답
 */
export interface GmailAirbnbAutoReplyJobItemResult {
  gmail_message_id: string;
  incoming_message_id: number | null;
  sent: boolean;
  skipped: boolean;
  skip_reason: string | null;
}

export interface GmailAirbnbAutoReplyJobResponse {
  total_parsed: number;
  total_ingested: number;
  total_target_messages: number;
  total_sent: number;
  total_skipped_already_sent: number;
  total_skipped_no_message: number;
  items: GmailAirbnbAutoReplyJobItemResult[];
}

/**
 * POST /api/v1/jobs/gmail/airbnb/auto-reply
 * → Gmail ingest + parsing + DB 저장 + 자동응답 발송까지
 */
export async function runGmailAirbnbAutoReplyJob(
  payload: Partial<GmailAirbnbAutoReplyJobRequest> = {},
): Promise<GmailAirbnbAutoReplyJobResponse> {
  const body: GmailAirbnbAutoReplyJobRequest = {
    max_results: payload.max_results ?? 20,
    newer_than_days: payload.newer_than_days ?? 1,
    extra_query: payload.extra_query ?? null,
    query: payload.query ?? null,
    force: payload.force ?? false,
  };

  // ❗ 반드시 return 해줘야 함
  return apiPost<GmailAirbnbAutoReplyJobResponse, GmailAirbnbAutoReplyJobRequest>(
    "/jobs/gmail/airbnb/auto-reply",
    body,
  );
}

/* ===================== 🔥 PREVIEW 파트 ===================== */

// 프리뷰 아이템
export interface GmailAirbnbAutoReplyPreviewItem {
  message_id: number;
  gmail_message_id: string;
  property_code: string | null;
  ota: string | null;
  guest_name: string | null;
  checkin_date: string | null;
  checkout_date: string | null;
  pure_guest_message: string | null;
  intent: string | null;
  fine_intent: string | null;
  reply_text: string | null;
  generation_mode: string | null;
  allow_auto_send: boolean | null;
}

// 프리뷰 응답
export interface GmailAirbnbAutoReplyPreviewResponse {
  total_parsed: number;
  total_ingested: number;
  total_preview_generated: number;
  preview_items: GmailAirbnbAutoReplyPreviewItem[];
}

/**
 * POST /api/v1/jobs/gmail/airbnb/auto-reply/preview
 * → Gmail ingest + parsing + DB 저장 + Intent/FineIntent 분석
 *   + LLM reply_text 생성까지 (발송 X)
 */
export async function runGmailAirbnbAutoReplyPreviewJob(
  payload: Partial<GmailAirbnbAutoReplyJobRequest> = {},
): Promise<GmailAirbnbAutoReplyPreviewResponse> {
  const body: GmailAirbnbAutoReplyJobRequest = {
    max_results: payload.max_results ?? 20,
    newer_than_days: payload.newer_than_days ?? 1,
    extra_query: payload.extra_query ?? null,
    query: payload.query ?? null,
    force: payload.force ?? false,
  };

  // ❗ 여기도 반드시 return
  return apiPost<
    GmailAirbnbAutoReplyPreviewResponse,
    GmailAirbnbAutoReplyJobRequest
  >("/jobs/gmail/auto-reply/preview", body);
}
