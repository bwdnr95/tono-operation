// frontend/src/api/commitments.ts
/**
 * Commitment Memory API
 */
import { apiGet, apiPost } from "./client";

import type {
  CommitmentListResponse,
  RiskSignalListResponse,
  ConflictCheckRequest,
  ConflictCheckResponse,
} from "../types/commitments";

// ============================================================
// Commitments
// ============================================================

/**
 * 대화의 Commitment 목록 조회
 * GET /api/v1/conversations/{thread_id}/commitments
 */
export async function getCommitments(
  threadId: string,
  params?: { status?: string }
): Promise<CommitmentListResponse> {
  return apiGet<CommitmentListResponse>(
    `/conversations/${threadId}/commitments`,
    params
  );
}

// ============================================================
// Risk Signals
// ============================================================

/**
 * 대화의 Risk Signal 목록 조회
 * GET /api/v1/conversations/{thread_id}/risk-signals
 */
export async function getRiskSignals(
  threadId: string,
  params?: { include_resolved?: boolean }
): Promise<RiskSignalListResponse> {
  return apiGet<RiskSignalListResponse>(
    `/conversations/${threadId}/risk-signals`,
    params
  );
}

/**
 * Risk Signal 해결 처리
 * POST /api/v1/conversations/{thread_id}/risk-signals/{signal_id}/resolve
 */
export async function resolveRiskSignal(
  threadId: string,
  signalId: string
): Promise<{ status: string; signal_id: string }> {
  return apiPost<{ status: string; signal_id: string }>(
    `/conversations/${threadId}/risk-signals/${signalId}/resolve`,
    {}
  );
}

// ============================================================
// Conflict Check
// ============================================================

/**
 * Draft 충돌 검사
 * POST /api/v1/conversations/{thread_id}/check-conflicts
 */
export async function checkDraftConflicts(
  threadId: string,
  draftText: string
): Promise<ConflictCheckResponse> {
  return apiPost<ConflictCheckResponse, ConflictCheckRequest>(
    `/conversations/${threadId}/check-conflicts`,
    { draft_text: draftText }
  );
}

/**
 * LLM Context용 Commitment 문자열 조회 (디버깅용)
 * GET /api/v1/conversations/{thread_id}/commitment-context
 */
export async function getCommitmentContext(
  threadId: string
): Promise<{ thread_id: string; commitment_context: string }> {
  return apiGet<{ thread_id: string; commitment_context: string }>(
    `/conversations/${threadId}/commitment-context`
  );
}
