// src/api/staffNotifications.ts
/**
 * Staff Notification API (OC 기반)
 * 
 * Staff Notification = Operational Commitment 기반
 * "약속 존재"가 아니라 "운영 리스크 발생 시점"만 노출
 */
import { apiGet, apiPost } from "./client";

// ============================================================
// Types
// ============================================================

export type OCPriority = "immediate" | "upcoming" | "pending";
export type OCStatus = "pending" | "done" | "resolved" | "suggested_resolve";

export interface StaffNotificationDTO {
  oc_id: string;
  conversation_id: string;
  airbnb_thread_id: string;  // 백엔드 필드명에 맞춤
  topic: string;
  description: string;
  evidence_quote: string;
  priority: OCPriority;
  guest_name: string | null;
  property_code: string | null;
  property_name: string | null;
  checkin_date: string | null;
  checkout_date: string | null;
  status: OCStatus;
  resolution_reason: string | null;
  resolution_evidence: string | null;  // 해소 제안 근거 (게스트 메시지)
  is_candidate_only: boolean;
  target_time_type: string;
  target_date: string | null;
  created_at: string | null;
}

export interface StaffNotificationListResponse {
  items: StaffNotificationDTO[];
  total: number;
  as_of: string;
}

export interface OCDTO {
  id: string;
  conversation_id: string;
  topic: string;
  description: string;
  evidence_quote: string;
  target_time_type: string;
  target_date: string | null;
  status: OCStatus;
  resolution_reason: string | null;
  resolution_evidence: string | null;  // 해소 제안 근거
  is_candidate_only: boolean;
  created_at: string;
}

export interface OCListResponse {
  airbnb_thread_id: string;  // 백엔드 필드명에 맞춤
  items: OCDTO[];
  total: number;
}

export interface OCActionResponse {
  oc_id: string;
  status: string;
  action: string;
  success: boolean;
}

// ============================================================
// Topic/Priority Labels
// ============================================================

export const OC_TOPIC_LABELS: Record<string, string> = {
  early_checkin: "얼리체크인",
  follow_up: "후속 안내",
  facility_issue: "시설 문제",
  refund_check: "환불 확인",
  payment: "결제",
  compensation: "보상",
};

export const OC_PRIORITY_STYLES: Record<OCPriority, { bg: string; text: string; border: string; label: string }> = {
  immediate: {
    bg: "bg-rose-500/20",
    text: "text-rose-300",
    border: "border-rose-500/40",
    label: "🔴 즉시",
  },
  upcoming: {
    bg: "bg-amber-500/20",
    text: "text-amber-300",
    border: "border-amber-500/40",
    label: "🟡 예정",
  },
  pending: {
    bg: "bg-slate-500/20",
    text: "text-slate-300",
    border: "border-slate-500/40",
    label: "⚪ 대기",
  },
};

export const OC_STATUS_LABELS: Record<OCStatus, string> = {
  pending: "대기",
  done: "완료",
  resolved: "해소",
  suggested_resolve: "해소 제안",
};

// ============================================================
// API Functions
// ============================================================

/**
 * Staff Notification Action Queue 조회
 * GET /api/v1/staff-notifications
 */
export async function fetchStaffNotifications(params?: {
  limit?: number;
}): Promise<StaffNotificationListResponse> {
  return apiGet<StaffNotificationListResponse>("/staff-notifications", params);
}

/**
 * 단일 OC 조회
 * GET /api/v1/staff-notifications/{oc_id}
 */
export async function getOC(ocId: string): Promise<OCDTO> {
  return apiGet<OCDTO>(`/staff-notifications/${ocId}`);
}

/**
 * Conversation의 OC 목록 조회 (Backlog)
 * GET /api/v1/staff-notifications/conversations/{thread_id}/ocs
 */
export async function getConversationOCs(
  threadId: string,
  params?: { include_resolved?: boolean }
): Promise<OCListResponse> {
  return apiGet<OCListResponse>(
    `/staff-notifications/conversations/${threadId}/ocs`,
    params
  );
}

/**
 * OC 완료 처리
 * POST /api/v1/staff-notifications/{oc_id}/done
 */
export async function markOCDone(ocId: string): Promise<OCActionResponse> {
  return apiPost<OCActionResponse>(`/staff-notifications/${ocId}/done`, {});
}

/**
 * suggested_resolve 확정
 * POST /api/v1/staff-notifications/{oc_id}/confirm-resolve
 */
export async function confirmOCResolve(ocId: string): Promise<OCActionResponse> {
  return apiPost<OCActionResponse>(`/staff-notifications/${ocId}/confirm-resolve`, {});
}

/**
 * suggested_resolve 거부
 * POST /api/v1/staff-notifications/{oc_id}/reject-resolve
 */
export async function rejectOCResolve(ocId: string): Promise<OCActionResponse> {
  return apiPost<OCActionResponse>(`/staff-notifications/${ocId}/reject-resolve`, {});
}

/**
 * 후보 확정
 * POST /api/v1/staff-notifications/{oc_id}/confirm-candidate
 */
export async function confirmOCCandidate(ocId: string): Promise<OCActionResponse> {
  return apiPost<OCActionResponse>(`/staff-notifications/${ocId}/confirm-candidate`, {});
}

/**
 * 후보 거부
 * POST /api/v1/staff-notifications/{oc_id}/reject-candidate
 */
export async function rejectOCCandidate(ocId: string): Promise<OCActionResponse> {
  return apiPost<OCActionResponse>(`/staff-notifications/${ocId}/reject-candidate`, {});
}

/**
 * 우선순위 변경
 * POST /api/v1/staff-notifications/{oc_id}/change-priority
 * 
 * - immediate: target_date = today
 * - upcoming: target_date = today + 1
 * - pending: target_date 유지
 */
export async function changeOCPriority(
  ocId: string, 
  priority: OCPriority
): Promise<OCActionResponse> {
  return apiPost<OCActionResponse>(`/staff-notifications/${ocId}/change-priority`, { priority });
}
