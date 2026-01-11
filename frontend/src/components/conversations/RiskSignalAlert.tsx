// src/components/conversations/RiskSignalAlert.tsx
import type { RiskSignalDTO, RiskSeverity } from "../../types/commitments";

const SEVERITY_STYLES: Record<RiskSeverity, { badgeClass: string; bgColor: string; textColor: string }> = {
  low: { badgeClass: "badge-default", bgColor: "var(--bg-secondary)", textColor: "var(--text-secondary)" },
  medium: { badgeClass: "badge-warning", bgColor: "var(--warning-bg)", textColor: "var(--warning)" },
  high: { badgeClass: "badge-warning", bgColor: "var(--warning-bg)", textColor: "var(--warning)" },
  critical: { badgeClass: "badge-danger", bgColor: "var(--danger-bg)", textColor: "var(--danger)" },
};

const SEVERITY_LABELS: Record<RiskSeverity, string> = {
  low: "참고",
  medium: "주의",
  high: "경고",
  critical: "위험",
};

function SignalCard({ signal, onDismiss }: { signal: RiskSignalDTO; onDismiss?: (id: string) => void }) {
  const style = SEVERITY_STYLES[signal.severity] || SEVERITY_STYLES.medium;

  return (
    <div 
      className="card" 
      style={{ 
        background: style.bgColor, 
        borderColor: style.textColor,
        borderWidth: "1px",
        borderStyle: "solid"
      }}
    >
      <div style={{ padding: "12px 16px", display: "flex", alignItems: "flex-start", gap: "12px" }}>
        <span style={{ fontSize: "16px", color: style.textColor }}>⚠</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <span className={`badge ${style.badgeClass}`} style={{ fontSize: "10px" }}>
              {SEVERITY_LABELS[signal.severity]}
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>
              {new Date(signal.created_at).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
          <p style={{ fontSize: "13px", color: style.textColor, whiteSpace: "pre-wrap" }}>{signal.message}</p>
        </div>
        {onDismiss && (
          <button 
            onClick={() => onDismiss(signal.id)} 
            className="btn btn-ghost btn-sm"
            style={{ padding: "4px 8px" }}
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

interface Props {
  signals: RiskSignalDTO[];
  onDismiss?: (id: string) => void;
  loading?: boolean;
}

export function RiskSignalAlert({ signals, onDismiss, loading }: Props) {
  if (loading) {
    return (
      <div className="card" style={{ padding: "16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "13px", color: "var(--text-secondary)" }}>
          <div className="loading-spinner" style={{ width: "16px", height: "16px" }} />
          약속 충돌 확인 중...
        </div>
      </div>
    );
  }

  if (!signals.length) return null;

  const sorted = [...signals].sort((a, b) => {
    const order: Record<RiskSeverity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    return order[a.severity] - order[b.severity];
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {sorted.map((s) => (
        <SignalCard key={s.id} signal={s} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

// Conflict Confirm Modal
interface ConflictConfirmModalProps {
  isOpen: boolean;
  conflicts: Array<{ has_conflict: boolean; severity?: RiskSeverity; message: string }>;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConflictConfirmModal({ isOpen, conflicts, onConfirm, onCancel }: ConflictConfirmModalProps) {
  if (!isOpen) return null;

  const hasHighSeverity = conflicts.some((c) => c.severity === "high" || c.severity === "critical");

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ maxWidth: "480px" }}>
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontSize: "20px", color: hasHighSeverity ? "var(--danger)" : "var(--warning)" }}>⚠</span>
            <div>
              <h3 className="modal-title">약속 충돌 감지</h3>
              <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>발송 전 확인이 필요합니다</p>
            </div>
          </div>
        </div>

        <div className="modal-body" style={{ maxHeight: "300px", overflow: "auto" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {conflicts.map((conflict, idx) => {
              const style = SEVERITY_STYLES[conflict.severity || "medium"];
              return (
                <div 
                  key={idx} 
                  style={{ 
                    background: style.bgColor,
                    borderRadius: "var(--radius)",
                    padding: "12px",
                    border: `1px solid ${style.textColor}`
                  }}
                >
                  <p style={{ fontSize: "13px", color: style.textColor, whiteSpace: "pre-wrap" }}>{conflict.message}</p>
                </div>
              );
            })}
          </div>
        </div>

        <div className="modal-footer">
          <button onClick={onCancel} className="btn btn-secondary">
            취소
          </button>
          <button
            onClick={onConfirm}
            className="btn"
            style={{ 
              background: hasHighSeverity ? "var(--danger)" : "var(--warning)", 
              color: "white" 
            }}
          >
            그래도 발송
          </button>
        </div>
      </div>
    </div>
  );
}
