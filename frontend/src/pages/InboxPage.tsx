// src/pages/InboxPage.tsx
import React from "react";
import { bulkSend } from "../api/conversations";
import type { ConversationDetailDTO, ConversationListItemDTO } from "../types/conversations";
import type { RiskSignalDTO, ConflictDTO } from "../types/commitments";
import { ConversationDetail } from "../components/conversations/ConversationDetail";
import { canBulkSend } from "../components/conversations/OutcomeLabelDisplay";
import {
  generateDraftReply,
  getBulkEligibleConversations,
  getConversationDetail,
  getConversations,
  patchDraftReply,
  sendConversation,
  ingestGmailMessages,
  markConversationRead,
} from "../api/conversations";
import { getRiskSignals, resolveRiskSignal, checkDraftConflicts } from "../api/commitments";
import { useConversationStore } from "../store/conversationStore";

function isoNowMinusHours(h: number) {
  return new Date(Date.now() - h * 60 * 60 * 1000).toISOString();
}

function formatTime(v: string) {
  try {
    return new Date(v).toLocaleString("ko-KR", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return v;
  }
}

type BulkRow = {
  conversation_id: string;
  airbnb_thread_id: string;
  selected: boolean;
  guest_name?: string | null;
  checkin_date?: string | null;
  checkout_date?: string | null;
  draft_content?: string | null;
  outcome_label?: any | null;
};

type BulkSendRowResult = {
  conversation_id: string;
  airbnb_thread_id: string;
  result: "sent" | "skipped" | "failed";
  message?: string;
};

export const InboxPage: React.FC = () => {
  // Store
  const {
    allConversations,
    conversationDetails,
    isReadFilter,
    statusFilter,
    safetyFilter,
    threadIdFilter,
    selectedId,
    isInitialized,
    listLoading,
    detailLoading,
    error: storeError,
    setAllConversations,
    setConversationDetail,
    setIsReadFilter,
    setStatusFilter,
    setSafetyFilter,
    setThreadIdFilter,
    setSelectedId,
    setListLoading,
    setDetailLoading,
    setError: setStoreError,
    markAsRead,
    getFilteredConversations,
  } = useConversationStore();

  const filteredItems = getFilteredConversations();

  // Local state
  const [detail, setDetail] = React.useState<ConversationDetailDTO | null>(null);
  const [detailError, setDetailError] = React.useState<string | null>(null);
  const [draftContent, setDraftContent] = React.useState("");
  const [generating, setGenerating] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [lastActionMsg, setLastActionMsg] = React.useState<string | null>(null);

  // Bulk
  const [bulkOpen, setBulkOpen] = React.useState(false);
  const [bulkLoading, setBulkLoading] = React.useState(false);
  const [bulkError, setBulkError] = React.useState<string | null>(null);
  const [bulkRows, setBulkRows] = React.useState<BulkRow[]>([]);
  const [bulkSending, setBulkSending] = React.useState(false);
  const [bulkResults, setBulkResults] = React.useState<BulkSendRowResult[] | null>(null);

  // Gmail
  const [ingesting, setIngesting] = React.useState(false);
  const [ingestResult, setIngestResult] = React.useState<string | null>(null);

  // Risk/Conflict
  const [riskSignals, setRiskSignals] = React.useState<RiskSignalDTO[]>([]);
  const [riskSignalsLoading, setRiskSignalsLoading] = React.useState(false);
  const [conflicts, setConflicts] = React.useState<ConflictDTO[]>([]);
  const [showConflictModal, setShowConflictModal] = React.useState(false);
  const [pendingSend, setPendingSend] = React.useState(false);

  // ===== Initial Load =====
  React.useEffect(() => {
    if (isInitialized) return;
    const fetchAll = async () => {
      setListLoading(true);
      try {
        const res = await getConversations({
          channel: "gmail",
          limit: 200,
        });
        setAllConversations(res.items);
        if (res.items.length > 0) {
          const firstUnread = res.items.find(c => !c.is_read);
          setSelectedId(firstUnread?.id || res.items[0].id);
        }
      } catch (e: any) {
        setStoreError(e?.message ?? "목록 조회 실패");
      } finally {
        setListLoading(false);
      }
    };
    fetchAll();
  }, [isInitialized]);

  // ===== Detail Load =====
  React.useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const cached = conversationDetails[selectedId];
    if (cached) {
      setDetail(cached);
      setDraftContent(cached.draft_reply?.content ?? "");
      return;
    }
    const fetchDetail = async () => {
      setDetailLoading(true);
      setDetailError(null);
      setRiskSignals([]);
      try {
        const d = await getConversationDetail(selectedId);
        setDetail(d);
        setConversationDetail(selectedId, d);
        setDraftContent(d.draft_reply?.content ?? "");
        if (d.conversation?.airbnb_thread_id) {
          try {
            const signalRes = await getRiskSignals(d.conversation.airbnb_thread_id);
            setRiskSignals(signalRes.signals || []);
          } catch {}
        }
      } catch (e: any) {
        setDetailError(e?.message ?? "상세 조회 실패");
      } finally {
        setDetailLoading(false);
      }
    };
    fetchDetail();
  }, [selectedId, conversationDetails]);

  // ===== Actions =====
  const onTabChange = (tab: boolean | null) => {
    setIsReadFilter(tab);
    const filtered = allConversations
      .filter(c => (tab === null ? true : c.is_read === tab))
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    if (filtered.length > 0) setSelectedId(filtered[0].id);
    else setSelectedId(null);
  };

  const onRefresh = async () => {
    setListLoading(true);
    try {
      const res = await getConversations({ channel: "gmail", limit: 200 });
      setAllConversations(res.items);
    } catch (e: any) {
      setStoreError(e?.message ?? "새로고침 실패");
    } finally {
      setListLoading(false);
    }
  };

  const onGenerateDraft = async () => {
    if (!detail) return;
    setGenerating(true);
    try {
      const res = await generateDraftReply(detail.conversation.id);
      setDraftContent(res.draft_reply?.content ?? "");
      setLastActionMsg("초안 생성 완료");
      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
      setConversationDetail(detail.conversation.id, refreshed);
    } catch (e: any) {
      setDetailError(e?.message ?? "초안 생성 실패");
    } finally {
      setGenerating(false);
    }
  };

  const onSaveDraft = async () => {
    if (!detail || !draftContent.trim()) return;
    setSaving(true);
    try {
      await patchDraftReply(detail.conversation.id, draftContent);
      setLastActionMsg("초안 저장 완료");
      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
      setConversationDetail(detail.conversation.id, refreshed);
    } catch (e: any) {
      setDetailError(e?.message ?? "초안 저장 실패");
    } finally {
      setSaving(false);
    }
  };

  const executeSend = async () => {
    if (!detail) return;
    setSending(true);
    try {
      await sendConversation(detail.conversation.id, { draft_reply_id: detail.draft_reply!.id });
      setLastActionMsg("발송 완료");
      await onRefresh();
      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
      setConversationDetail(detail.conversation.id, refreshed);
    } catch (e: any) {
      setDetailError(e?.message ?? "발송 실패");
    } finally {
      setSending(false);
    }
  };

  const onSend = async () => {
    if (!detail?.draft_reply?.id) return;
    if (detail.draft_reply.safety_status === "block") {
      setDetailError("safety_status가 block이므로 발송 불가");
      return;
    }
    if (detail.conversation.status !== "ready_to_send" && detail.conversation.status !== "blocked") {
      setDetailError("status가 ready_to_send가 아님");
      return;
    }
    try {
      const conflictRes = await checkDraftConflicts(detail.conversation.airbnb_thread_id, draftContent);
      if (conflictRes.has_any_conflict) {
        setConflicts(conflictRes.conflicts);
        setShowConflictModal(true);
        return;
      }
    } catch {}
    await executeSend();
  };

  const onMarkRead = async () => {
    if (!detail) return;
    markAsRead(detail.conversation.id);
    setLastActionMsg("처리완료");
    try {
      await markConversationRead(detail.conversation.id);
    } catch {}
  };

  const onDismissRiskSignal = async (signalId: string) => {
    if (!detail?.conversation?.airbnb_thread_id) return;
    try {
      await resolveRiskSignal(detail.conversation.airbnb_thread_id, signalId);
      setRiskSignals(prev => prev.filter(s => s.id !== signalId));
    } catch {}
  };

  const onIngestGmail = async () => {
    setIngesting(true);
    setIngestResult(null);
    try {
      const res = await ingestGmailMessages();
      setIngestResult(`✓ ${res.total_conversations}개 대화 처리됨`);
      await onRefresh();
    } catch (e: any) {
      setIngestResult(`✗ 실패: ${e?.message}`);
    } finally {
      setIngesting(false);
    }
  };

  // ===== Bulk =====
  const openBulk = async () => {
    setBulkOpen(true);
    setBulkLoading(true);
    setBulkError(null);
    setBulkResults(null);
    try {
      const res = await getBulkEligibleConversations();
      const rows = await Promise.all(
        res.items.map(async (it) => {
          try {
            const d = await getConversationDetail(it.id);
            return {
              conversation_id: it.id,
              airbnb_thread_id: it.airbnb_thread_id,
              selected: canBulkSend(d.draft_reply?.outcome_label),
              guest_name: d.messages?.find(m => m.guest_name)?.guest_name ?? it.guest_name,
              checkin_date: it.checkin_date,
              checkout_date: it.checkout_date,
              draft_content: d.draft_reply?.content ?? null,
              outcome_label: d.draft_reply?.outcome_label ?? null,
            };
          } catch {
            return {
              conversation_id: it.id,
              airbnb_thread_id: it.airbnb_thread_id,
              selected: true,
              guest_name: it.guest_name,
              checkin_date: it.checkin_date,
              checkout_date: it.checkout_date,
              draft_content: null,
              outcome_label: null,
            };
          }
        })
      );
      setBulkRows(rows);
    } catch (e: any) {
      setBulkError(e?.message ?? "Bulk 조회 실패");
    } finally {
      setBulkLoading(false);
    }
  };

  const runBulkSend = async () => {
    const selected = bulkRows.filter(r => r.selected);
    if (!selected.length) {
      setBulkError("선택된 대화가 없습니다");
      return;
    }
    setBulkSending(true);
    try {
      const res = await bulkSend(selected.map(r => r.conversation_id));
      setBulkResults(res.results.map(r => ({
        conversation_id: r.conversation_id,
        airbnb_thread_id: selected.find(s => s.conversation_id === r.conversation_id)?.airbnb_thread_id ?? "",
        result: r.result,
        message: r.error_message ?? undefined,
      })));
      await onRefresh();
    } catch (e: any) {
      setBulkError(e?.message ?? "Bulk send 실패");
    } finally {
      setBulkSending(false);
    }
  };

  // ===== Render =====
  const unreadCount = allConversations.filter(c => !c.is_read).length;
  const readCount = allConversations.filter(c => c.is_read).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", position: "relative" }}>
      {/* Loading Overlay for Gmail Ingest */}
      {ingesting && (
        <div className="loading-overlay">
          <div className="card" style={{ padding: "32px 48px", textAlign: "center" }}>
            <div className="loading-spinner" style={{ margin: "0 auto 16px" }} />
            <p style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
              Gmail에서 메일을 불러오는 중...
            </p>
          </div>
        </div>
      )}

      {/* Page Header */}
      <header className="page-header">
        <div className="page-header-content">
          <div>
            <h1 className="page-title">Inbox</h1>
            <p className="page-subtitle">게스트 메시지 관리 · AI 초안 생성 · 발송 승인</p>
            {ingestResult && <p style={{ fontSize: "12px", color: "var(--success)", marginTop: "4px" }}>{ingestResult}</p>}
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button onClick={onRefresh} disabled={listLoading} className="btn btn-secondary">
              {listLoading ? "로딩..." : "새로고침"}
            </button>
            <button onClick={onIngestGmail} disabled={ingesting} className="btn btn-secondary">
              📥 메일 불러오기
            </button>
            <button onClick={openBulk} className="btn btn-primary">
              Bulk Send
            </button>
          </div>
        </div>
      </header>

      {/* Stats Row */}
      <div style={{ padding: "16px 32px", display: "flex", gap: "16px" }}>
        <div className="stat-card" style={{ flex: 1 }}>
          <div className="stat-label">안읽음</div>
          <div className="stat-value" style={{ color: "var(--warning)" }}>{unreadCount}</div>
        </div>
        <div className="stat-card" style={{ flex: 1 }}>
          <div className="stat-label">처리완료</div>
          <div className="stat-value" style={{ color: "var(--success)" }}>{readCount}</div>
        </div>
        <div className="stat-card" style={{ flex: 1 }}>
          <div className="stat-label">전체</div>
          <div className="stat-value">{allConversations.length}</div>
        </div>
      </div>

      {/* Tabs + Filters */}
      <div style={{ padding: "0 32px 16px", display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
        <div className="tabs">
          <button onClick={() => onTabChange(false)} className={`tab ${isReadFilter === false ? "active" : ""}`}>
            안읽음
          </button>
          <button onClick={() => onTabChange(true)} className={`tab ${isReadFilter === true ? "active" : ""}`}>
            처리완료
          </button>
          <button onClick={() => onTabChange(null)} className={`tab ${isReadFilter === null ? "active" : ""}`}>
            전체
          </button>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input
            value={threadIdFilter}
            onChange={(e) => setThreadIdFilter(e.target.value)}
            placeholder="Thread ID 검색..."
            className="input"
            style={{ width: "180px" }}
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="select" style={{ width: "120px" }}>
            <option value="">상태 전체</option>
            <option value="open">대기중</option>
            <option value="needs_review">검토필요</option>
            <option value="ready_to_send">발송준비</option>
            <option value="sent">발송완료</option>
            <option value="blocked">실패</option>
          </select>
          <select value={safetyFilter} onChange={(e) => setSafetyFilter(e.target.value)} className="select" style={{ width: "100px" }}>
            <option value="">Safety</option>
            <option value="pass">Pass</option>
            <option value="review">Review</option>
            <option value="block">Block</option>
          </select>
        </div>

        {storeError && <span style={{ color: "var(--danger)", fontSize: "13px" }}>{storeError}</span>}
      </div>

      {/* Main Content */}
      <div className="inbox-layout">
        {/* List */}
        <div className="inbox-list card">
          <div className="card-header">
            <span className="card-title">대화 목록</span>
            <span className="badge badge-default">{filteredItems.length}</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {listLoading ? (
              <div className="empty-state">
                <div className="loading-spinner" />
              </div>
            ) : filteredItems.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📭</div>
                <div className="empty-state-title">대화가 없습니다</div>
                <div className="empty-state-text">필터를 변경하거나 메일을 불러오세요</div>
              </div>
            ) : (
              filteredItems.map(item => (
                <div
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                  className={`conversation-item ${item.id === selectedId ? "selected" : ""}`}
                >
                  <div className="conversation-avatar">
                    {item.guest_name?.charAt(0) || "?"}
                  </div>
                  <div className="conversation-content">
                    <div className="conversation-name">
                      {item.guest_name || "게스트"}
                      {item.property_code && (
                        <span className="badge badge-primary" style={{ marginLeft: "8px", padding: "2px 8px", fontSize: "10px" }}>
                          {item.property_code}
                        </span>
                      )}
                    </div>
                    {item.checkin_date && item.checkout_date && (
                      <div className="conversation-preview">
                        {item.checkin_date} → {item.checkout_date}
                      </div>
                    )}
                    <div className="conversation-meta">
                      <span className={`badge ${item.status === "ready_to_send" ? "badge-success" : item.status === "needs_review" ? "badge-warning" : item.status === "blocked" ? "badge-danger" : "badge-default"}`}>
                        {item.status === "ready_to_send" ? "발송준비" : item.status === "needs_review" ? "검토필요" : item.status === "sent" ? "완료" : item.status === "blocked" ? "실패" : "대기"}
                      </span>
                      <span className="conversation-time">{formatTime(item.updated_at)}</span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Detail */}
        <div className="inbox-detail card">
          {detailLoading ? (
            <div className="empty-state" style={{ flex: 1 }}>
              <div className="loading-spinner" />
            </div>
          ) : detailError ? (
            <div className="empty-state" style={{ flex: 1 }}>
              <div className="empty-state-text">{detailError}</div>
            </div>
          ) : (
            <ConversationDetail
              detail={detail}
              loading={detailLoading}
              error={detailError}
              draftContent={draftContent}
              onChangeDraftContent={setDraftContent}
              onGenerateDraft={onGenerateDraft}
              onSaveDraft={onSaveDraft}
              onSend={onSend}
              generating={generating}
              saving={saving}
              sending={sending}
              lastActionMsg={lastActionMsg}
              onMarkRead={onMarkRead}
              riskSignals={riskSignals}
              riskSignalsLoading={riskSignalsLoading}
              onDismissRiskSignal={onDismissRiskSignal}
              conflicts={conflicts}
              showConflictModal={showConflictModal}
              onConfirmSendWithConflict={() => { setShowConflictModal(false); executeSend(); }}
              onCancelSendWithConflict={() => setShowConflictModal(false)}
            />
          )}
        </div>
      </div>

      {/* Bulk Modal */}
      {bulkOpen && (
        <div className="modal-overlay">
          <div className="modal" style={{ maxWidth: "700px" }}>
            <div className="modal-header">
              <h2 className="modal-title">Bulk Send</h2>
              <button onClick={() => setBulkOpen(false)} className="btn btn-ghost btn-sm">✕</button>
            </div>
            <div className="modal-body">
              {bulkLoading ? (
                <div className="empty-state"><div className="loading-spinner" /></div>
              ) : bulkRows.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-text">발송 가능한 대화가 없습니다</div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {bulkRows.map(row => (
                    <label key={row.conversation_id} style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "12px",
                      padding: "12px",
                      background: row.selected ? "rgba(99,102,241,0.05)" : "var(--bg)",
                      borderRadius: "var(--radius)",
                      cursor: "pointer"
                    }}>
                      <input
                        type="checkbox"
                        checked={row.selected}
                        onChange={e => setBulkRows(prev => prev.map(r => r.conversation_id === row.conversation_id ? { ...r, selected: e.target.checked } : r))}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600 }}>{row.guest_name || "게스트"}</div>
                        {row.draft_content && (
                          <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
                            {row.draft_content.slice(0, 100)}...
                          </div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              )}
              {bulkError && <div style={{ color: "var(--danger)", marginTop: "12px" }}>{bulkError}</div>}
              {bulkResults && (
                <div style={{ marginTop: "16px" }}>
                  <div style={{ fontWeight: 600, marginBottom: "8px" }}>결과</div>
                  {bulkResults.map(r => (
                    <div key={r.conversation_id} style={{ fontSize: "13px", padding: "4px 0" }}>
                      <span className={`badge ${r.result === "sent" ? "badge-success" : "badge-danger"}`}>{r.result}</span>
                      <span style={{ marginLeft: "8px" }}>{r.airbnb_thread_id}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={() => setBulkOpen(false)} className="btn btn-secondary">닫기</button>
              <button onClick={runBulkSend} disabled={bulkSending || !bulkRows.some(r => r.selected)} className="btn btn-primary">
                {bulkSending ? "발송 중..." : `${bulkRows.filter(r => r.selected).length}개 발송`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
