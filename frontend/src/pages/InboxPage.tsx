// src/pages/InboxPage.tsx
import React from "react";
import { LoadingOverlay } from "../components/ui/LoadingOverlay";

import {
  getConversations,
  getConversationDetail,
  generateDraftReply,
  patchDraftReply,
  previewSend,
  sendConversation,
  getBulkEligibleConversations,
  bulkPreview,
  bulkSend,
  type GetConversationsResponse,
} from "../api/conversations";

import type {
  ConversationDetailDTO,
  ConversationListItemDTO,
  BulkSendPreviewResponseDTO,
  BulkSendSendResponseDTO,
} from "../types/conversations";

import { ConversationList } from "../components/conversations/ConversationList";
import { ConversationDetail } from "../components/conversations/ConversationDetail";
import { usePreviewStore } from "../store/previewStore";

function isoNowMinusHours(h: number) {
  return new Date(Date.now() - h * 60 * 60 * 1000).toISOString();
}

type BulkRow = {
  conversation_id: string;
  thread_id: string;
  selected: boolean;
};

export const InboxPage: React.FC = () => {
  // filters
  const [threadIdFilter, setThreadIdFilter] = React.useState<string>("");
  const [statusFilter, setStatusFilter] = React.useState<
    "open" | "needs_review" | "ready_to_send" | "sent" | "blocked" | ""
  >("");
  const [safetyFilter, setSafetyFilter] = React.useState<
    "pass" | "review" | "block" | ""
  >("");
  const [updatedSince, setUpdatedSince] = React.useState<string>(() =>
    isoNowMinusHours(48),
  );

  // list
  const [items, setItems] = React.useState<ConversationListItemDTO[]>([]);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [listLoading, setListLoading] = React.useState(false);
  const [listError, setListError] = React.useState<string | null>(null);

  // selection
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  // detail
  const [detail, setDetail] = React.useState<ConversationDetailDTO | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [detailError, setDetailError] = React.useState<string | null>(null);

  // draft editor
  const [draftContent, setDraftContent] = React.useState<string>("");
  const [generating, setGenerating] = React.useState(false);
  const [saving, setSaving] = React.useState(false);

  // send flow
  const [previewing, setPreviewing] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [lastActionMsg, setLastActionMsg] = React.useState<string | null>(null);

  // preview store
  const setDraft = usePreviewStore((s) => s.setDraft);
  const setSendPreview = usePreviewStore((s) => s.setSendPreview);
  const clearSendPreview = usePreviewStore((s) => s.clearSendPreview);
  const sendPreviewByConversation = usePreviewStore(
    (s) => s.sendPreviewByConversation,
  );

  const bulkPreviewState = usePreviewStore((s) => s.bulkPreview);
  const setBulkPreviewState = usePreviewStore((s) => s.setBulkPreview);
  const bulkSendResult = usePreviewStore((s) => s.bulkSendResult);
  const setBulkSendResult = usePreviewStore((s) => s.setBulkSendResult);

  // bulk modal state
  const [bulkOpen, setBulkOpen] = React.useState(false);
  const [bulkLoading, setBulkLoading] = React.useState(false);
  const [bulkError, setBulkError] = React.useState<string | null>(null);
  const [bulkRows, setBulkRows] = React.useState<BulkRow[]>([]);
  const [bulkPreviewing, setBulkPreviewing] = React.useState(false);
  const [bulkSending, setBulkSending] = React.useState(false);

  const selectedSendPreview = selectedId
    ? sendPreviewByConversation[selectedId] ?? null
    : null;

  /* ===================== List/Detail ===================== */
  const fetchList = React.useCallback(
    async (cursor: string | null, replace: boolean) => {
      setListLoading(true);
      setListError(null);

      try {
        const res: GetConversationsResponse = await getConversations({
          channel: "gmail",
          thread_id: threadIdFilter ? threadIdFilter : null,
          status: statusFilter ? statusFilter : null,
          safety_status: safetyFilter ? safetyFilter : null,
          updated_since: updatedSince ? updatedSince : null,
          limit: 50,
          cursor: cursor ?? null,
        });

        setNextCursor(res.next_cursor ?? null);
        setItems((prev) => (replace ? res.items : [...prev, ...res.items]));
        if (replace && res.items.length) setSelectedId(res.items[0].id);
      } catch (e: any) {
        console.error(e);
        setListError(e?.message ?? "Conversation(thread) 목록 조회 실패");
      } finally {
        setListLoading(false);
      }
    },
    [threadIdFilter, statusFilter, safetyFilter, updatedSince],
  );

  const fetchDetail = React.useCallback(
    async (conversationId: string) => {
      setDetailLoading(true);
      setDetailError(null);
      setLastActionMsg(null);

      try {
        const d = await getConversationDetail(conversationId);
        setDetail(d);
        setDraftContent(d.draft_reply?.content ?? "");
        clearSendPreview(conversationId);
      } catch (e: any) {
        console.error(e);
        setDetailError(e?.message ?? "Conversation 상세 조회 실패");
        setDetail(null);
        setDraftContent("");
      } finally {
        setDetailLoading(false);
      }
    },
    [clearSendPreview],
  );

  React.useEffect(() => {
    fetchList(null, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    if (selectedId) fetchDetail(selectedId);
  }, [selectedId, fetchDetail]);

  const onClickSearch = async () => {
    setItems([]);
    setNextCursor(null);
    setSelectedId(null);
    setDetail(null);
    await fetchList(null, true);
  };

  const onLoadMore = async () => {
    if (!nextCursor) return;
    await fetchList(nextCursor, false);
  };

  /* ===================== Draft ===================== */
  const onGenerateDraft = async () => {
    if (!detail) return;

    setGenerating(true);
    setDetailError(null);
    setLastActionMsg(null);

    try {
      const res = await generateDraftReply(detail.conversation.id);

      // thread_id invariant
      if (
        !res.draft_reply.thread_id ||
        res.draft_reply.thread_id !== detail.conversation.thread_id
      ) {
        setDetailError(
          "DraftReply.thread_id 누락 또는 Conversation.thread_id와 불일치: 발송 금지",
        );
        return;
      }

      setDraft(detail.conversation.id, res.draft_reply);
      setDraftContent(res.draft_reply.content);
      clearSendPreview(detail.conversation.id);
      setLastActionMsg("초안 생성 완료");

      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
    } catch (e: any) {
      console.error(e);
      setDetailError(e?.message ?? "초안 생성 실패");
    } finally {
      setGenerating(false);
    }
  };

  const onSaveDraft = async () => {
    if (!detail) return;
    if (!draftContent.trim()) {
      setDetailError("content는 필수입니다.");
      return;
    }

    setSaving(true);
    setDetailError(null);
    setLastActionMsg(null);

    try {
      const res = await patchDraftReply(detail.conversation.id, draftContent);

      // thread_id invariant
      if (
        !res.draft_reply.thread_id ||
        res.draft_reply.thread_id !== detail.conversation.thread_id
      ) {
        setDetailError(
          "DraftReply.thread_id 누락 또는 Conversation.thread_id와 불일치: 발송 금지",
        );
        return;
      }

      setDraft(detail.conversation.id, res.draft_reply);
      clearSendPreview(detail.conversation.id);
      setLastActionMsg("초안 저장 완료");

      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
    } catch (e: any) {
      console.error(e);
      setDetailError(e?.message ?? "초안 저장 실패");
    } finally {
      setSaving(false);
    }
  };

  /* ===================== Preview / Send ===================== */
  const onPreviewSend = async () => {
    if (!detail) return;

    // must have draft with thread_id
    if (!detail.draft_reply?.id || !detail.draft_reply.thread_id) {
      setDetailError("draft_reply(thread_id 포함) 없이 preview 불가");
      return;
    }
    if (detail.draft_reply.thread_id !== detail.conversation.thread_id) {
      setDetailError(
        "draft_reply.thread_id와 conversation.thread_id 불일치: preview/send 금지",
      );
      return;
    }

    setPreviewing(true);
    setDetailError(null);
    setLastActionMsg(null);

    try {
      const p = await previewSend(detail.conversation.id);

      if (!p.thread_id || p.thread_id !== detail.conversation.thread_id) {
        setDetailError("send:preview thread_id 불일치: 발송 금지");
        clearSendPreview(detail.conversation.id);
        return;
      }

      setSendPreview(detail.conversation.id, p);
      setLastActionMsg(`send:preview 완료 (can_send=${String(p.can_send)})`);
    } catch (e: any) {
      console.error(e);
      setDetailError(e?.message ?? "send:preview 실패");
      clearSendPreview(detail.conversation.id);
    } finally {
      setPreviewing(false);
    }
  };

  const onSend = async () => {
    if (!detail) return;

    const p = sendPreviewByConversation[detail.conversation.id] ?? null;
    if (!p) {
      setDetailError("send:preview confirm_token이 없습니다. 먼저 Preview를 실행하세요.");
      return;
    }
    if (p.thread_id !== detail.conversation.thread_id) {
      setDetailError("confirm_token의 thread_id가 현재 Conversation과 불일치: 발송 금지");
      return;
    }
    if (!p.can_send || p.safety_status !== "pass") {
      setDetailError("can_send=false 또는 safety_status!=pass 입니다. 발송할 수 없습니다.");
      return;
    }
    if (detail.conversation.status !== "ready_to_send") {
      setDetailError("conversation.status가 ready_to_send가 아닙니다. 발송할 수 없습니다.");
      return;
    }

    setSending(true);
    setDetailError(null);
    setLastActionMsg(null);

    try {
      await sendConversation(detail.conversation.id, {
        draft_reply_id: p.draft_reply_id,
        confirm_token: p.confirm_token,
      });

      clearSendPreview(detail.conversation.id);
      setLastActionMsg("발송 완료");

      await fetchList(null, true);
      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
    } catch (e: any) {
      console.error(e);
      setDetailError(e?.message ?? "발송 실패");
    } finally {
      setSending(false);
    }
  };

  /* ===================== Bulk Send ===================== */
  const openBulk = async () => {
    setBulkOpen(true);
    setBulkError(null);
    setBulkSendResult(null);
    setBulkPreviewState(null);

    setBulkLoading(true);
    try {
      const res = await getBulkEligibleConversations({
        channel: "gmail",
        updated_since: updatedSince,
      });

      const rows: BulkRow[] = (res.items ?? []).map((it) => ({
        conversation_id: it.id,
        thread_id: it.thread_id,
        selected: true,
      }));
      setBulkRows(rows);
    } catch (e: any) {
      console.error(e);
      setBulkError(e?.message ?? "Bulk eligible 조회 실패");
      setBulkRows([]);
    } finally {
      setBulkLoading(false);
    }
  };

  const runBulkPreview = async () => {
    setBulkError(null);

    const ids = bulkRows.filter((r) => r.selected).map((r) => r.conversation_id);
    if (!ids.length) {
      setBulkError("선택된 Conversation(thread)이 없습니다.");
      return;
    }

    setBulkPreviewing(true);
    try {
      const res: BulkSendPreviewResponseDTO = await bulkPreview({
        conversation_ids: ids,
      });
      setBulkPreviewState(res);
    } catch (e: any) {
      console.error(e);
      setBulkError(e?.message ?? "Bulk preview 실패");
      setBulkPreviewState(null);
    } finally {
      setBulkPreviewing(false);
    }
  };

  const runBulkSend = async () => {
    setBulkError(null);

    const pv = bulkPreviewState;
    if (!pv?.job?.id || !pv.confirm_token) {
      setBulkError("Bulk send는 preview(job.id + confirm_token) 이후에만 가능합니다.");
      return;
    }

    setBulkSending(true);
    try {
      const res: BulkSendSendResponseDTO = await bulkSend(pv.job.id, {
        confirm_token: pv.confirm_token,
      });
      setBulkSendResult(res);
      await fetchList(null, true);
    } catch (e: any) {
      console.error(e);
      setBulkError(e?.message ?? "Bulk send 실패");
    } finally {
      setBulkSending(false);
    }
  };

  return (
    <div className="relative flex flex-1 min-h-0 flex-col gap-4">
      {/* header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="block text-lg font-semibold text-slate-100 leading-tight">
            TONO Inbox (Thread Conversation)
          </h1>
          <p className="block mt-1 text-xs text-slate-400 leading-tight">
            Conversation = (channel=gmail, thread_id). Draft/Preview/Send 모두
            thread_id 귀속 필수.
          </p>
        </div>

        <button
          type="button"
          onClick={openBulk}
          className="shrink-0 rounded-full bg-sky-500 px-3 py-1.5 text-[11px] font-semibold text-slate-950 hover:bg-sky-400"
        >
          Bulk Send
        </button>
      </div>

      {/* Filters */}
      <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
          <div className="md:col-span-4">
            <div className="text-[11px] font-semibold text-slate-400">
              thread_id (optional)
            </div>
            <input
              value={threadIdFilter}
              onChange={(e) => setThreadIdFilter(e.target.value)}
              placeholder="gmail thread id"
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-slate-700"
            />
          </div>

          <div className="md:col-span-2">
            <div className="text-[11px] font-semibold text-slate-400">status</div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-700"
            >
              <option value="">(all)</option>
              <option value="open">open</option>
              <option value="needs_review">needs_review</option>
              <option value="ready_to_send">ready_to_send</option>
              <option value="sent">sent</option>
              <option value="blocked">blocked</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <div className="text-[11px] font-semibold text-slate-400">
              safety_status
            </div>
            <select
              value={safetyFilter}
              onChange={(e) => setSafetyFilter(e.target.value as any)}
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-700"
            >
              <option value="">(all)</option>
              <option value="pass">pass</option>
              <option value="review">review</option>
              <option value="block">block</option>
            </select>
          </div>

          <div className="md:col-span-4">
            <div className="text-[11px] font-semibold text-slate-400">
              updated_since (ISO8601)
            </div>
            <input
              value={updatedSince}
              onChange={(e) => setUpdatedSince(e.target.value)}
              placeholder="2025-01-01T00:00:00.000Z"
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-slate-700"
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onClickSearch}
            className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1.5 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/10"
          >
            조회
          </button>
          <button
            type="button"
            onClick={onLoadMore}
            disabled={!nextCursor || listLoading}
            className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1.5 text-[11px] font-semibold text-slate-200 hover:bg-slate-900/50 disabled:opacity-60"
            title={!nextCursor ? "next_cursor 없음" : ""}
          >
            더 보기
          </button>
          {listError ? (
            <span className="text-[11px] text-rose-300">{listError}</span>
          ) : null}
        </div>
      </section>

      {/* Main */}
      <section className="grid flex-1 min-h-0 grid-cols-1 gap-4 md:grid-cols-12">
        <div className="md:col-span-4 min-h-0">
          <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/60">
            <div className="flex items-center justify-between border-b border-slate-900 px-4 py-3">
              <div className="text-xs font-semibold text-slate-300">Threads</div>
              <div className="text-[11px] text-slate-500">{items.length}개</div>
            </div>

            {listLoading ? (
              <LoadingOverlay message="목록 로딩 중..." />
            ) : (
              <ConversationList
                items={items}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            )}
          </div>
        </div>

        <div className="md:col-span-8 min-h-0">
          <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/60">
            {detailLoading ? (
              <LoadingOverlay message="상세 로딩 중..." />
            ) : (
              <ConversationDetail
                detail={detail}
                loading={detailLoading}
                error={detailError}
                draftContent={draftContent}
                onChangeDraftContent={(v) => {
                  setDraftContent(v);
                  if (detail) clearSendPreview(detail.conversation.id);
                }}
                onGenerateDraft={onGenerateDraft}
                onSaveDraft={onSaveDraft}
                sendPreview={selectedSendPreview}
                onPreviewSend={onPreviewSend}
                onSend={onSend}
                generating={generating}
                saving={saving}
                previewing={previewing}
                sending={sending}
                lastActionMsg={lastActionMsg}
              />
            )}
          </div>
        </div>
      </section>

      {/* ================= Bulk Send Modal ================= */}
      {bulkOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
              <div>
                <div className="text-sm font-semibold text-slate-100">
                  Bulk Send (Thread Conversation)
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  선택된 thread별 검토 완료 응답만 발송됩니다.
                </div>
              </div>

              <button
                onClick={() => setBulkOpen(false)}
                className="text-sm text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>

            <div className="flex flex-1 min-h-0 flex-col gap-4 overflow-y-auto px-5 py-4">
              {bulkLoading ? (
                <div className="text-sm text-slate-400">대상 조회 중...</div>
              ) : bulkRows.length === 0 ? (
                <div className="text-sm text-slate-500">
                  Bulk Send 가능한 Conversation(thread)이 없습니다.
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    {bulkRows.map((row) => (
                      <label
                        key={row.conversation_id}
                        className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 hover:bg-slate-900"
                      >
                        <input
                          type="checkbox"
                          checked={row.selected}
                          onChange={(e) =>
                            setBulkRows((prev) =>
                              prev.map((r) =>
                                r.conversation_id === row.conversation_id
                                  ? { ...r, selected: e.target.checked }
                                  : r,
                              ),
                            )
                          }
                        />
                        <div className="min-w-0">
                          <div className="truncate text-xs font-mono text-slate-200">
                            thread_id: {row.thread_id}
                          </div>
                          <div className="text-[10px] text-slate-500">
                            conversation_id: {row.conversation_id}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>

                  {bulkError ? (
                    <div className="text-xs text-rose-300">{bulkError}</div>
                  ) : null}

                  {bulkPreviewState ? (
                    <div className="mt-4 space-y-3">
                      <div className="text-xs font-semibold text-slate-300">
                        Bulk Preview Result
                      </div>

                      {bulkPreviewState.previews.map((p) => (
                        <div
                          key={p.conversation_id}
                          className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                            <span className="font-mono">
                              conversation_id: {p.conversation_id}
                            </span>
                            <span className="font-mono">
                              thread_id: {p.thread_id}
                            </span>
                            <span>safety: {p.safety_status}</span>
                            <span>can_send: {String(p.can_send)}</span>
                          </div>

                          {p.preview_content ? (
                            <div className="mt-2 whitespace-pre-wrap text-xs text-slate-100">
                              {p.preview_content}
                            </div>
                          ) : (
                            <div className="mt-2 text-xs text-slate-500">
                              {p.blocked_reason ?? "preview 불가"}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {bulkSendResult ? (
                    <div className="mt-4 space-y-2">
                      <div className="text-xs font-semibold text-slate-300">
                        Bulk Send Result: {bulkSendResult.status}
                      </div>
                      {bulkSendResult.results.map((r) => (
                        <div
                          key={r.conversation_id}
                          className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-[11px] text-slate-400 font-mono">
                              thread_id: {r.thread_id}
                            </div>
                            <div className="text-[11px] font-semibold text-slate-200">
                              {r.result}
                            </div>
                          </div>
                          {r.result !== "sent" ? (
                            <div className="mt-1 text-[11px] text-rose-300">
                              {r.error_code ? `${r.error_code}: ` : ""}
                              {r.error_message ?? ""}
                            </div>
                          ) : (
                            <div className="mt-1 text-[11px] text-emerald-300">
                              sent_at: {r.sent_at ?? ""}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-slate-800 px-5 py-4">
              <div className="flex items-center gap-2">
                <button
                  onClick={runBulkPreview}
                  disabled={bulkPreviewing}
                  className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1.5 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/10 disabled:opacity-60"
                >
                  {bulkPreviewing ? "Preview 중..." : "Bulk Preview"}
                </button>

                <button
                  onClick={runBulkSend}
                  disabled={
                    bulkSending ||
                    !bulkPreviewState?.job?.id ||
                    !bulkPreviewState?.confirm_token
                  }
                  className="rounded-full bg-sky-500 px-3 py-1.5 text-[11px] font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-60"
                  title="Bulk Preview 이후에만 발송 가능"
                >
                  {bulkSending ? "발송 중..." : "Bulk Send"}
                </button>
              </div>

              <button
                onClick={() => setBulkOpen(false)}
                className="text-xs text-slate-400 hover:text-slate-200"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
