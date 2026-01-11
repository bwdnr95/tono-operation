// src/components/conversations/ConversationDetail.tsx
import React from "react";
import type { ConversationDetailDTO, ThreadMessageDTO, SendActionLogDTO } from "../../types/conversations";
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

// 발송 액션 표시 컴포넌트
function SendActionBadge({ action }: { action: string }) {
  if (action === "auto_sent") {
    return (
      <span 
        className="badge badge-info" 
        style={{ 
          display: "inline-flex", 
          alignItems: "center", 
          gap: "4px",
          background: "var(--primary-bg)",
          color: "var(--primary)",
        }}
        title="AI가 자동으로 발송했습니다"
      >
        🤖 자동발송
      </span>
    );
  }
  if (action === "send") {
    return (
      <span className="badge badge-success" style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
        ✓ 수동발송
      </span>
    );
  }
  if (action === "bulk_send") {
    return (
      <span className="badge badge-default" style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
        📦 일괄발송
      </span>
    );
  }
  return <span className="badge badge-default">{action}</span>;
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
  // 🆕 객실 배정
  onOpenRoomAssignment?: () => void;
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
    onOpenRoomAssignment,
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
  const sendLogs = detail.send_logs || [];
  const canReply = detail.can_reply ?? true;
  const airbnbActionUrl = detail.airbnb_action_url;

  // 마지막 발송 액션 (있으면)
  const lastSendLog = sendLogs.length > 0 ? sendLogs[0] : null;

  // 발송 조건: draft 존재 + thread_id 일치 + safety가 block이 아님 + status가 ready_to_send 또는 blocked(재시도) + can_reply
  const canSend =
    canReply &&
    !!draft?.id &&
    !!draft.airbnb_thread_id &&
    draft.airbnb_thread_id === c.airbnb_thread_id &&
    draft.safety_status !== "block" &&
    (c.status === "ready_to_send" || c.status === "blocked");

  // Guest info from conversation (reservation_info 기반)
  const guestName = c.guest_name;
  const checkinDate = c.checkin_date;
  const checkoutDate = c.checkout_date;
  const isInquiry = c.reservation_status === "inquiry";
  const dateAvailability = detail.date_availability;

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
                  {isInquiry && (
                    <span className="badge" style={{ padding: "2px 8px", fontSize: "10px", background: "var(--primary-bg)", color: "var(--primary)" }}>
                      💬 문의
                    </span>
                  )}
                  {c.property_code ? (
                    /* 객실 배정됨 - 클릭하면 변경 가능 */
                    c.group_code ? (
                      <button
                        className="badge badge-primary"
                        onClick={onOpenRoomAssignment}
                        style={{ 
                          padding: "2px 8px", 
                          fontSize: "10px",
                          cursor: "pointer",
                          border: "none",
                        }}
                        title="클릭하여 객실 변경"
                      >
                        {c.property_code}
                      </button>
                    ) : (
                      /* 그룹 없이 직접 매핑된 숙소 - 변경 불가 */
                      <span className="badge badge-primary" style={{ padding: "2px 8px", fontSize: "10px" }}>
                        {c.property_code}
                      </span>
                    )
                  ) : c.group_code ? (
                    /* 그룹 매핑이지만 객실 미배정 */
                    <button
                      className="badge"
                      onClick={onOpenRoomAssignment}
                      style={{ 
                        padding: "2px 8px", 
                        fontSize: "10px", 
                        background: "var(--warning-bg)", 
                        color: "var(--warning)",
                        border: "1px dashed var(--warning)",
                        cursor: "pointer",
                      }}
                    >
                      🏠 객실 배정 필요
                    </button>
                  ) : null}
                </div>
                {checkinDate && checkoutDate && (
                  <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                    {formatDate(checkinDate)} → {formatDate(checkoutDate)}
                  </div>
                )}
                {/* 예약 가능 여부 표시 (INQUIRY 상태일 때) */}
                {isInquiry && dateAvailability && (
                  <div style={{ marginTop: "4px" }}>
                    {dateAvailability.available ? (
                      <span style={{ 
                        display: "inline-flex", 
                        alignItems: "center", 
                        gap: "4px",
                        padding: "2px 8px", 
                        fontSize: "11px", 
                        background: "var(--success-bg)", 
                        color: "var(--success)",
                        borderRadius: "4px",
                      }}>
                        ✅ 해당 날짜 예약 가능
                      </span>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                        <span style={{ 
                          display: "inline-flex", 
                          alignItems: "center", 
                          gap: "4px",
                          padding: "2px 8px", 
                          fontSize: "11px", 
                          background: "var(--danger-bg)", 
                          color: "var(--danger)",
                          borderRadius: "4px",
                        }}>
                          ❌ 해당 날짜 예약 불가
                        </span>
                        {dateAvailability.conflicts.map((conflict, idx) => (
                          <span key={idx} style={{ 
                            fontSize: "10px", 
                            color: "var(--danger)",
                            marginLeft: "8px",
                          }}>
                            → {conflict.guest_name}님 ({formatDate(conflict.checkin_date)}~{formatDate(conflict.checkout_date)})
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontWeight: 600 }}>게스트</span>
              {isInquiry && (
                <span className="badge" style={{ padding: "2px 8px", fontSize: "10px", background: "var(--primary-bg)", color: "var(--primary)" }}>
                  💬 문의
                </span>
              )}
              {c.property_code ? (
                c.group_code ? (
                  <button
                    className="badge badge-primary"
                    onClick={onOpenRoomAssignment}
                    style={{ 
                      padding: "2px 8px", 
                      fontSize: "10px",
                      cursor: "pointer",
                      border: "none",
                    }}
                    title="클릭하여 객실 변경"
                  >
                    {c.property_code}
                  </button>
                ) : (
                  <span className="badge badge-primary" style={{ padding: "2px 8px", fontSize: "10px" }}>
                    {c.property_code}
                  </span>
                )
              ) : c.group_code ? (
                <button
                  className="badge"
                  onClick={onOpenRoomAssignment}
                  style={{ 
                    padding: "2px 8px", 
                    fontSize: "10px", 
                    background: "var(--warning-bg)", 
                    color: "var(--warning)",
                    border: "1px dashed var(--warning)",
                    cursor: "pointer",
                  }}
                >
                  🏠 객실 배정 필요
                </button>
              ) : null}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span className={`badge ${c.status === "ready_to_send" ? "badge-success" : c.status === "needs_review" ? "badge-warning" : c.status === "blocked" ? "badge-danger" : "badge-default"}`}>
            {c.status === "ready_to_send" ? "발송준비" : c.status === "needs_review" ? "검토필요" : c.status === "sent" ? "완료" : c.status === "blocked" ? "실패" : "대기"}
          </span>
          {/* 발송 완료된 경우 발송 방식 표시 */}
          {c.status === "sent" && lastSendLog && (
            <SendActionBadge action={lastSendLog.action} />
          )}
          <span className={`badge ${c.safety_status === "pass" ? "badge-success" : c.safety_status === "review" ? "badge-warning" : "badge-danger"}`}>
            {c.safety_status === "pass" ? "안전" : c.safety_status === "review" ? "검토" : "차단"}
          </span>
          {/* 에어비앤비 링크 버튼 */}
          {c.airbnb_thread_id && (
            <a
              href={`https://www.airbnb.co.kr/hosting/thread/${c.airbnb_thread_id}?thread_type=home_booking`}
              target="_blank"
              rel="noopener noreferrer"
              title="에어비앤비에서 대화 보기"
              className="btn btn-ghost btn-sm"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                color: "#FF385C",
                textDecoration: "none",
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.373 0 0 5.373 0 12c0 5.623 3.872 10.328 9.092 11.63a.75.75 0 0 0 .908-.657c.13-.738.324-1.526.578-2.344a.75.75 0 0 0-.263-.795C8.047 18.06 6.5 15.193 6.5 12c0-3.038 2.462-5.5 5.5-5.5s5.5 2.462 5.5 5.5c0 3.193-1.547 6.06-3.815 7.834a.75.75 0 0 0-.263.795c.254.818.448 1.606.578 2.344a.75.75 0 0 0 .908.657C20.128 22.328 24 17.623 24 12c0-6.627-5.373-12-12-12z"/>
              </svg>
              Airbnb
            </a>
          )}
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
          {canReply ? (
            <button
              onClick={onSend}
              disabled={sending || !canSend}
              className="btn btn-primary composer-send"
              title={!canSend ? "발송 조건: safety pass, status ready_to_send" : ""}
            >
              {sending ? "발송 중..." : "발송 →"}
            </button>
          ) : (
            <a
              href={airbnbActionUrl || "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="btn composer-send"
              style={{ 
                background: "#ff385c", 
                color: "white",
                textDecoration: "none",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15,3 21,3 21,9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              에어비앤비
            </a>
          )}
        </div>

        {/* 문의 단계 안내 */}
        {!canReply && (
          <div style={{ 
            marginTop: "12px", 
            padding: "12px", 
            background: "var(--primary-bg)", 
            borderRadius: "var(--radius)", 
            color: "var(--primary)", 
            fontSize: "13px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}>
            <span>💬</span>
            <span>문의 단계에서는 에어비앤비에서 직접 답변해주세요. 예약 확정 후 TONO에서 자동 응답이 가능합니다.</span>
          </div>
        )}

        {error && (
          <div style={{ marginTop: "12px", padding: "12px", background: "var(--danger-bg)", borderRadius: "var(--radius)", color: "var(--danger)", fontSize: "13px" }}>
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
