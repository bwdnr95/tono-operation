// src/components/conversations/ConversationDetail.tsx
import React from "react";
import type { ConversationDetailDTO, SendPreviewDTO, SafetyStatus, MessageDirection } from "../../types/conversations";

function fmt(v: string) {
  try {
    return new Date(v).toLocaleString("ko-KR");
  } catch {
    return v;
  }
}

function safetyPill(s: SafetyStatus) {
  if (s === "pass") return <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-200">pass</span>;
  if (s === "review") return <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-200">review</span>;
  return <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-semibold text-rose-200">block</span>;
}

function dirPill(d: MessageDirection) {
  if (d === "incoming") return <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold text-sky-200">incoming</span>;
  return <span className="rounded-full bg-slate-500/15 px-2 py-0.5 text-[10px] font-semibold text-slate-200">outgoing</span>;
}

export function ConversationDetail(props: {
  detail: ConversationDetailDTO | null;
  loading: boolean;
  error: string | null;

  draftContent: string;
  onChangeDraftContent: (v: string) => void;

  onGenerateDraft: () => void | Promise<void>;
  onSaveDraft: () => void | Promise<void>;

  sendPreview: SendPreviewDTO | null;
  onPreviewSend: () => void | Promise<void>;
  onSend: () => void | Promise<void>;

  generating: boolean;
  saving: boolean;
  previewing: boolean;
  sending: boolean;

  lastActionMsg: string | null;
}) {
  const {
    detail,
    loading,
    error,
    draftContent,
    onChangeDraftContent,
    onGenerateDraft,
    onSaveDraft,
    sendPreview,
    onPreviewSend,
    onSend,
    generating,
    saving,
    previewing,
    sending,
    lastActionMsg,
  } = props;

  if (loading) return <div className="p-4 text-xs text-slate-400">상세 로딩 중...</div>;
  if (!detail) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-xs text-slate-500">
        좌측에서 thread Conversation을 선택하세요.
      </div>
    );
  }

  const c = detail.conversation;
  const draft = detail.draft_reply;

  const canPreview = !!draft && c.thread_id && c.channel === "gmail";
  const canSend =
    !!sendPreview &&
    sendPreview.can_send === true &&
    sendPreview.safety_status === "pass" &&
    c.status === "ready_to_send" &&
    sendPreview.thread_id === c.thread_id;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4 md:p-5">
      {/* Meta */}
      <section className="rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-100">
              Conversation (thread canonical){" "}
              <span className="ml-2 font-mono text-[12px] text-slate-400">{c.id}</span>
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              channel: <span className="font-mono">{c.channel}</span> · thread_id:{" "}
              <span className="font-mono">{c.thread_id}</span>
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-700/30 px-2 py-0.5 text-[10px] font-semibold text-slate-300">
                status: {c.status}
              </span>
              <span className="rounded-full bg-slate-700/30 px-2 py-0.5 text-[10px] font-semibold text-slate-300">
                safety: {c.safety_status} {safetyPill(c.safety_status)}
              </span>
              <span className="rounded-full bg-slate-700/30 px-2 py-0.5 text-[10px] font-semibold text-slate-300">
                last_message_id: <span className="font-mono">{c.last_message_id ?? "null"}</span>
              </span>
            </div>
          </div>

          <div className="text-right text-[11px] text-slate-500">
            <div>created: {fmt(c.created_at)}</div>
            <div>updated: {fmt(c.updated_at)}</div>
          </div>
        </div>

        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
          <div className="mb-1 text-[10px] font-semibold text-slate-400">thread_id invariant</div>
          <div className="text-[11px] text-slate-400">
            Outgoing 응답은 반드시 동일 thread_id로 귀속되어야 합니다. (thread_id 누락 시 발송 금지)
          </div>
        </div>
      </section>

      {/* Messages */}
      <section className="rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3">
        <h2 className="text-xs font-semibold text-slate-300">thread messages</h2>

        <div className="mt-3 space-y-2">
          {detail.messages?.length ? (
            detail.messages.map((m) => (
              <div key={m.id} className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                <div className="flex items-center justify-between gap-2 text-[10px] text-slate-500">
                  <div className="flex items-center gap-2">
                    {dirPill(m.direction)}
                    <span className="font-mono">msg_id: {m.id}</span>
                    <span className="font-mono">thread: {m.thread_id}</span>
                  </div>
                  <span>{fmt(m.created_at)}</span>
                </div>
                <div className="mt-1 whitespace-pre-wrap text-[12px] text-slate-100">{m.content}</div>
              </div>
            ))
          ) : (
            <div className="text-[11px] text-slate-500">메시지가 없습니다.</div>
          )}
        </div>
      </section>

      {/* Draft */}
      <section className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs font-semibold text-slate-300">draft (thread 귀속 필수)</h2>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onGenerateDraft}
              disabled={generating}
              className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1.5 text-[11px] font-semibold text-sky-200 hover:bg-sky-500/10 disabled:opacity-60"
            >
              {generating ? "생성 중..." : "초안 생성 (LLM)"}
            </button>
            <button
              type="button"
              onClick={onSaveDraft}
              disabled={saving || !draftContent.trim()}
              className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1.5 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/10 disabled:opacity-60"
            >
              {saving ? "저장 중..." : "초안 저장"}
            </button>
          </div>
        </div>

        <div className="text-[11px] text-slate-500">
          draft_id: <span className="font-mono text-slate-300">{draft?.id ?? "(null)"}</span>{" "}
          · thread_id: <span className="font-mono text-slate-300">{draft?.thread_id ?? "(null)"}</span>{" "}
          · safety: <span className="font-mono text-slate-300">{draft?.safety_status ?? "(null)"}</span>
        </div>

        <textarea
          value={draftContent}
          onChange={(e) => onChangeDraftContent(e.target.value)}
          placeholder="thread 컨텍스트 기반 초안"
          className="min-h-[160px] w-full resize-y rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-slate-700"
        />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={onPreviewSend}
            disabled={previewing || !canPreview}
            className="rounded-full bg-amber-500 px-3 py-1.5 text-[11px] font-semibold text-slate-950 hover:bg-amber-400 disabled:opacity-60"
            title={!canPreview ? "draft + thread_id 필요" : ""}
          >
            {previewing ? "Preview 중..." : "Send Preview"}
          </button>

          <button
            type="button"
            onClick={onSend}
            disabled={sending || !canSend}
            className="rounded-full bg-sky-500 px-3 py-1.5 text-[11px] font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-60"
            title={!canSend ? "confirm_token + thread_id match + can_send 필요" : ""}
          >
            {sending ? "발송 중..." : "확인 후 발송"}
          </button>
        </div>

        {sendPreview ? (
          <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
            <div className="mb-1 flex items-center justify-between">
              <div className="text-[10px] font-semibold text-slate-400">send:preview</div>
              {safetyPill(sendPreview.safety_status)}
            </div>
            <div className="text-[11px] text-slate-400 font-mono">
              thread_id: {sendPreview.thread_id} · draft_reply_id: {sendPreview.draft_reply_id} · can_send:{" "}
              {String(sendPreview.can_send)} · token: {sendPreview.confirm_token.slice(0, 10)}...
            </div>
            <div className="mt-2 whitespace-pre-wrap text-[12px] text-slate-100">
              {sendPreview.preview_content}
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-slate-500">Send Preview 실행 시 confirm_token이 발급됩니다.</div>
        )}

        {error ? <div className="text-[11px] text-rose-300">{error}</div> : null}
        {lastActionMsg ? <div className="text-[11px] text-slate-400">{lastActionMsg}</div> : null}
      </section>
    </div>
  );
}
