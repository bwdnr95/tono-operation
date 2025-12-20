// frontend/src/components/conversations/CommitmentHistory.tsx
/**
 * Commitment 히스토리 컴포넌트
 * 
 * 사이드바에서 이전에 확정한 약속 목록을 표시
 */
import React from "react";
import type { CommitmentDTO } from "../../types/commitments";
import { COMMITMENT_TOPIC_LABELS, COMMITMENT_TYPE_LABELS } from "../../types/commitments";

interface CommitmentHistoryProps {
  commitments: CommitmentDTO[];
  loading?: boolean;
  error?: string | null;
}

// Type별 아이콘
function TypeIcon({ type }: { type: string }) {
  switch (type) {
    case "allowance":
      return (
        <svg className="h-4 w-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      );
    case "prohibition":
      return (
        <svg className="h-4 w-4 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      );
    case "fee":
      return (
        <svg className="h-4 w-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case "condition":
      return (
        <svg className="h-4 w-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    default:
      return (
        <svg className="h-4 w-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      );
  }
}

// Type별 배경색
function getTypeBgClass(type: string): string {
  switch (type) {
    case "allowance":
      return "bg-emerald-500/10 border-emerald-500/20";
    case "prohibition":
      return "bg-rose-500/10 border-rose-500/20";
    case "fee":
      return "bg-amber-500/10 border-amber-500/20";
    case "condition":
      return "bg-sky-500/10 border-sky-500/20";
    default:
      return "bg-slate-500/10 border-slate-500/20";
  }
}

// 개별 Commitment 카드
function CommitmentCard({ commitment }: { commitment: CommitmentDTO }) {
  const topicLabel = COMMITMENT_TOPIC_LABELS[commitment.topic] || commitment.topic;
  const typeLabel = COMMITMENT_TYPE_LABELS[commitment.type] || commitment.type;
  const bgClass = getTypeBgClass(commitment.type);

  return (
    <div className={`rounded-lg border ${bgClass} p-3`}>
      <div className="flex items-start gap-2">
        <TypeIcon type={commitment.type} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-slate-300">
              {topicLabel}
            </span>
            <span className="text-[10px] text-slate-500">
              {typeLabel}
            </span>
          </div>
          <p className="text-xs text-slate-400 line-clamp-2">
            {commitment.provenance_text}
          </p>
          <div className="mt-1.5 text-[10px] text-slate-600">
            {new Date(commitment.created_at).toLocaleString("ko-KR", {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export function CommitmentHistory({ commitments, loading, error }: CommitmentHistoryProps) {
  if (loading) {
    return (
      <div className="p-4">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          약속 히스토리 로딩 중...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </div>
      </div>
    );
  }

  if (!commitments || commitments.length === 0) {
    return (
      <div className="p-4">
        <div className="flex flex-col items-center gap-2 py-6 text-center">
          <svg className="h-8 w-8 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <p className="text-xs text-slate-500">
            아직 확정된 약속이 없습니다
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4">
      {/* 헤더 */}
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-slate-300">
          확정된 약속
        </h3>
        <span className="text-[10px] text-slate-500">
          {commitments.length}개
        </span>
      </div>

      {/* 약속 목록 */}
      <div className="space-y-2">
        {commitments.map((commitment) => (
          <CommitmentCard key={commitment.id} commitment={commitment} />
        ))}
      </div>
    </div>
  );
}
