// frontend/src/types/commitments.ts
/**
 * Commitment Memory 관련 타입 정의
 */

// ============================================================
// Commitment
// ============================================================

export interface CommitmentDTO {
  id: string;
  topic: string;
  type: string;
  value: Record<string, unknown>;
  provenance_text: string;
  status: string;
  extraction_confidence: number;
  created_at: string;
}

export interface CommitmentListResponse {
  thread_id: string;
  commitments: CommitmentDTO[];
  total: number;
}

// Topic 라벨
export const COMMITMENT_TOPIC_LABELS: Record<string, string> = {
  early_checkin: "얼리체크인",
  late_checkout: "레이트체크아웃",
  checkin_time: "체크인시간",
  checkout_time: "체크아웃시간",
  guest_count_change: "인원변경",
  free_provision: "무료제공",
  extra_fee: "추가요금",
  reservation_change: "예약변경",
  pet_policy: "반려동물",
  special_request: "특별요청",
  other: "기타",
};

// Type 라벨
export const COMMITMENT_TYPE_LABELS: Record<string, string> = {
  allowance: "허용",
  prohibition: "금지",
  fee: "요금",
  change: "변경",
  condition: "조건부",
};

// ============================================================
// Risk Signal
// ============================================================

export type RiskSeverity = "low" | "medium" | "high" | "critical";

export interface RiskSignalDTO {
  id: string;
  signal_type: string;
  severity: RiskSeverity;
  message: string;
  resolved: boolean;
  created_at: string;
  related_commitment_id?: string;
  details: Record<string, unknown>;
}

export interface RiskSignalListResponse {
  thread_id: string;
  signals: RiskSignalDTO[];
  total: number;
}

// Severity 스타일
export const RISK_SEVERITY_STYLES: Record<RiskSeverity, { bg: string; text: string; border: string }> = {
  low: {
    bg: "bg-slate-500/20",
    text: "text-slate-300",
    border: "border-slate-500/30",
  },
  medium: {
    bg: "bg-amber-500/20",
    text: "text-amber-300",
    border: "border-amber-500/30",
  },
  high: {
    bg: "bg-orange-500/20",
    text: "text-orange-300",
    border: "border-orange-500/30",
  },
  critical: {
    bg: "bg-rose-500/20",
    text: "text-rose-300",
    border: "border-rose-500/30",
  },
};

// ============================================================
// Conflict Check
// ============================================================

export interface ConflictCheckRequest {
  draft_text: string;
}

export interface ConflictDTO {
  has_conflict: boolean;
  type?: string;
  severity?: RiskSeverity;
  message: string;
  existing_commitment?: CommitmentDTO;
}

export interface ConflictCheckResponse {
  thread_id: string;
  conflicts: ConflictDTO[];
  has_any_conflict: boolean;
}
