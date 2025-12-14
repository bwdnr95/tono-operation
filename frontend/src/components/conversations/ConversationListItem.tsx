// src/components/conversations/ConversationListItem.tsx
import React from "react";
import type { ConversationListItemDTO, SafetyStatus, ConversationStatus } from "../../types/conversations";

function fmt(v: string) {
  try {
    return new Date(v).toLocaleString("ko-KR");
  } catch {
    return v;
  }
}

function pill(base: string) {
  return `rounded-full px-2 py-0.5 text-[10px] font-semibold ${base}`;
}

function safetyPill(s: SafetyStatus) {
  if (s === "pass") return <span className={pill("bg-emerald-500/15 text-emerald-200")}>safety: pass</span>;
  if (s === "review") return <span className={pill("bg-amber-500/15 text-amber-200")}>safety: review</span>;
  return <span className={pill("bg-rose-500/15 text-rose-200")}>safety: block</span>;
}

function statusPill(s: ConversationStatus) {
  if (s === "ready_to_send") return <span className={pill("bg-sky-500/15 text-sky-200")}>ready</span>;
  if (s === "needs_review") return <span className={pill("bg-amber-500/15 text-amber-200")}>needs_review</span>;
  if (s === "sent") return <span className={pill("bg-emerald-500/15 text-emerald-200")}>sent</span>;
  if (s === "blocked") return <span className={pill("bg-rose-500/15 text-rose-200")}>blocked</span>;
  return <span className={pill("bg-slate-500/15 text-slate-200")}>open</span>;
}

export function ConversationListItem(props: {
  item: ConversationListItemDTO;
  selected: boolean;
  onClick: () => void;
}) {
  const { item, selected, onClick } = props;

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "w-full px-4 py-3 text-left transition",
        selected ? "bg-slate-900/60" : "bg-transparent hover:bg-slate-900/40",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100">
            thread_id: <span className="font-mono text-[12px] text-slate-300">{item.thread_id}</span>
          </div>

          <div className="mt-1 text-[11px] text-slate-500">
            updated: {fmt(item.updated_at)}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className={pill("bg-slate-700/30 text-slate-300")}>channel: {item.channel}</span>
            {statusPill(item.status)}
            {safetyPill(item.safety_status)}
            <span className={pill("bg-slate-700/30 text-slate-300")}>
              last_message_id: <span className="font-mono">{item.last_message_id ?? "null"}</span>
            </span>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <div className="text-[10px] text-slate-500">{fmt(item.created_at)}</div>
          <div className="mt-1 text-[10px] font-semibold text-slate-400 font-mono">
            {item.id.slice(0, 8)}
          </div>
        </div>
      </div>
    </button>
  );
}
