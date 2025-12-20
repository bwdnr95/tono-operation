// src/components/conversations/ConversationDetail.tsx
import React from "react";
import type { ConversationDetailDTO, ThreadMessageDTO } from "../../types/conversations";
import type { RiskSignalDTO, ConflictDTO } from "../../types/commitments";
import { RiskSignalAlert, ConflictConfirmModal } from "./RiskSignalAlert";
import { OutcomeLabelCard, SafetyBadge } from "./OutcomeLabelDisplay";

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

function formatDate(v: string | null | undefined) {
  if (!v) return null;
  try {
    return new Date(v).toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  } catch {
    return v;
  }
}

interface Props {
  detail: ConversationDetailDTO | null;
  loading: boolean;
  error: string | null;
  draftContent: string;
  onChangeDraftContent: (v: string) => void;
  onGenerateDraft: () => void | Promise<void>;
  onSaveDraft: () => void | Promise<void>;
  onSend: () => void | Promise<void>;
  generating: boolean;
  saving: boolean;
  sending: boolean;
  lastActionMsg: string | null;
  onMarkRead?: () => void | Promise<void>;
  riskSignals?: RiskSignalDTO[];
  riskSignalsLoading?: boolean;
  onDismissRiskSignal?: (signalId: string) => void;
  conflicts?: ConflictDTO[];
  showConflictModal?: boolean;
  onConfirmSendWithConflict?: () => void;
  onCancelSendWithConflict?: () => void;
}

export function ConversationDetail(props: Props) {
  const {
    detail,
    loading,
    error,
    draftContent,
    onChangeDraftContent,
    onGenerateDraft,
    onSaveDraft,
    onSend,
    generating,
    saving,
    sending,
    lastActionMsg,
    onMarkRead,
    riskSignals = [],
    riskSignalsLoading = false,
    onDismissRiskSignal,
    conflicts = [],
    showConflictModal = false,
    onConfirmSendWithConflict,
    onCancelSendWithConflict,
  } = props;

  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail?.messages]);

  React.useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = textareaRef.current.scrollHeight + "px";
    }
  }, [draftContent]);

  if (loading) {
    return (
      <div className="empty-state" style={{ flex: 1 }}>
        <div className="loading-spinner" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="empty-state" style={{ flex: 1 }}>
        <div className="empty-state-icon">💬</div>
        <div className="empty-state-title">대화를 선택해주세요</div>
        <div className="empty-state-text">왼쪽 목록에서 대화를 선택하면 상세 내용이 표시됩니다</div>
      </div>
    );
  }

  const c = detail.conversation;
  const draft = detail.draft_reply;
  const messages = detail.messages || [];

  // 발송 조건: draft 존재 + thread_id 일치 + safety가 block이 아님 + status가 ready_to_send 또는 blocked(재시도)
  const canSend =
    !!draft?.id &&
    !!draft.airbnb_thread_id &&
    draft.airbnb_thread_id === c.airbnb_thread_id &&
    draft.safety_status !== "block" &&
    (c.status === "ready_to_send" || c.status === "blocked");

  // Guest info from conversation (reservation_info 기반)
  const guestName = c.guest_name;
  const checkinDate = c.checkin_date;
  const checkoutDate = c.checkout_date;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div className="card-header" style={{ borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {guestName ? (
            <>
              <div className="conversation-avatar" style={{ width: "36px", height: "36px", fontSize: "13px" }}>
                {guestName.charAt(0) || "G"}
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontWeight: 600 }}>{guestName}</span>
                  {c.property_code && (
                    <span className="badge badge-primary" style={{ padding: "2px 8px", fontSize: "10px" }}>
                      {c.property_code}
                    </span>
                  )}
                </div>
                {checkinDate && checkoutDate && (
                  <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                    {formatDate(checkinDate)} → {formatDate(checkoutDate)}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontWeight: 600 }}>게스트</span>
              {c.property_code && (
                <span className="badge badge-primary" style={{ padding: "2px 8px", fontSize: "10px" }}>
                  {c.property_code}
                </span>
              )}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span className={`badge ${c.status === "ready_to_send" ? "badge-success" : c.status === "needs_review" ? "badge-warning" : c.status === "blocked" ? "badge-danger" : "badge-default"}`}>
            {c.status === "ready_to_send" ? "발송준비" : c.status === "needs_review" ? "검토필요" : c.status === "sent" ? "완료" : c.status === "blocked" ? "실패" : "대기"}
          </span>
          <span className={`badge ${c.safety_status === "pass" ? "badge-success" : c.safety_status === "review" ? "badge-warning" : "badge-danger"}`}>
            {c.safety_status === "pass" ? "안전" : c.safety_status === "review" ? "검토" : "차단"}
          </span>
          {onMarkRead && (
            <button onClick={onMarkRead} className="btn btn-ghost btn-sm">
              처리완료
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="message-list" style={{ flex: 1, background: "var(--bg)" }}>
        {messages.length > 0 ? (
          messages.map((m, idx) => (
            <div key={m.id} className={`message ${m.direction === "incoming" ? "incoming" : "outgoing"}`}>
              <div className="message-bubble">
                {m.content}
              </div>
              <div className="message-time">{formatTime(m.created_at)}</div>
            </div>
          ))
        ) : (
          <div className="empty-state">
            <div className="empty-state-text">메시지가 없습니다</div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Composer */}
      <div className="composer">
        {/* Risk Signals */}
        {(riskSignals.length > 0 || riskSignalsLoading) && (
          <div style={{ marginBottom: "12px" }}>
            <RiskSignalAlert signals={riskSignals} loading={riskSignalsLoading} onDismiss={onDismissRiskSignal} />
          </div>
        )}

        {/* Outcome Label */}
        {draft?.outcome_label && (
          <div style={{ marginBottom: "12px" }}>
            <OutcomeLabelCard outcomeLabel={draft.outcome_label} humanOverride={draft.human_override} />
          </div>
        )}

        {/* Actions */}
        <div className="composer-actions">
          <button onClick={onGenerateDraft} disabled={generating} className="btn btn-secondary btn-sm">
            {generating ? "생성 중..." : "🤖 AI 초안 생성"}
          </button>
          <button onClick={onSaveDraft} disabled={saving || !draftContent.trim()} className="btn btn-secondary btn-sm">
            {saving ? "저장 중..." : "💾 저장"}
          </button>
          {lastActionMsg && (
            <span style={{ fontSize: "12px", color: "var(--success)", marginLeft: "8px" }}>
              ✓ {lastActionMsg}
            </span>
          )}
        </div>

        {/* Textarea + Send */}
        <div className="composer-input">
          <textarea
            ref={textareaRef}
            value={draftContent}
            onChange={(e) => onChangeDraftContent(e.target.value)}
            placeholder="답장을 입력하세요..."
            className="composer-textarea"
          />
          <button
            onClick={onSend}
            disabled={sending || !canSend}
            className="btn btn-primary composer-send"
            title={!canSend ? "발송 조건: safety pass, status ready_to_send" : ""}
          >
            {sending ? "발송 중..." : "발송 →"}
          </button>
        </div>

        {error && (
          <div style={{ marginTop: "12px", padding: "12px", background: "rgba(239,68,68,0.1)", borderRadius: "var(--radius)", color: "var(--danger)", fontSize: "13px" }}>
            {error}
          </div>
        )}
      </div>

      {/* Conflict Modal */}
      <ConflictConfirmModal
        isOpen={showConflictModal}
        conflicts={conflicts}
        onConfirm={onConfirmSendWithConflict || (() => {})}
        onCancel={onCancelSendWithConflict || (() => {})}
      />
    </div>
  );
}
