// src/components/conversations/OutcomeLabelDisplay.tsx
import React from "react";
import type {
  OutcomeLabel,
  HumanOverride,
  SafetyOutcome,
  QualityOutcome,
  ResponseOutcome,
} from "../../types/outcomeLabel";
import { SAFETY_OUTCOME_LABELS, QUALITY_OUTCOME_LABELS, RESPONSE_OUTCOME_LABELS } from "../../types/outcomeLabel";

// Safety Badge
export function SafetyBadge({ safety, compact = false }: { safety: SafetyOutcome; compact?: boolean }) {
  const config: Record<SafetyOutcome, { className: string; icon: string }> = {
    SAFE: { className: "badge-success", icon: "✓" },
    SENSITIVE: { className: "badge-warning", icon: "⚠" },
    HIGH_RISK: { className: "badge-danger", icon: "⚠" },
  };
  const cfg = config[safety] || config.SAFE;

  if (compact) {
    return (
      <span 
        className={`badge ${cfg.className}`} 
        style={{ width: "20px", height: "20px", padding: 0, justifyContent: "center" }}
        title={SAFETY_OUTCOME_LABELS[safety]}
      >
        {cfg.icon}
      </span>
    );
  }

  return (
    <span className={`badge ${cfg.className}`}>
      {cfg.icon} {SAFETY_OUTCOME_LABELS[safety]}
    </span>
  );
}

// Quality Badge
export function QualityBadge({ quality }: { quality: QualityOutcome }) {
  if (quality === "OK_TO_SEND") return null;
  
  const config: Record<QualityOutcome, { className: string }> = {
    OK_TO_SEND: { className: "badge-default" },
    REVIEW_REQUIRED: { className: "badge-warning" },
    LOW_CONFIDENCE: { className: "badge-default" },
  };
  const cfg = config[quality] || config.OK_TO_SEND;
  
  return (
    <span className={`badge ${cfg.className}`} style={{ fontSize: "10px" }}>
      {QUALITY_OUTCOME_LABELS[quality]}
    </span>
  );
}

// Response Type Badge
const RESPONSE_ICONS: Record<ResponseOutcome, string> = {
  ANSWERED_GROUNDED: "📋",
  DECLINED_BY_POLICY: "🚫",
  NEED_FOLLOW_UP: "⏳",
  ASK_CLARIFY: "❓",
};

export function ResponseTypeBadge({ response }: { response: ResponseOutcome }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "12px", color: "var(--text-secondary)" }}>
      {RESPONSE_ICONS[response]} {RESPONSE_OUTCOME_LABELS[response]}
    </span>
  );
}

// FAQ Keys Display
export function FaqKeysDisplay({ faqKeys }: { faqKeys: string[] }) {
  if (!faqKeys.length) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
      {faqKeys.map((key) => (
        <span 
          key={key} 
          className="badge badge-default"
          style={{ fontSize: "10px" }}
        >
          #{key}
        </span>
      ))}
    </div>
  );
}

// Outcome Label Card
interface OutcomeLabelCardProps {
  outcomeLabel: OutcomeLabel;
  humanOverride?: HumanOverride | null;
  onOverride?: (reason: string) => void;
  expanded?: boolean;
}

export function OutcomeLabelCard({ outcomeLabel, humanOverride, onOverride, expanded = false }: OutcomeLabelCardProps) {
  const [isExpanded, setIsExpanded] = React.useState(expanded);
  const [showOverrideForm, setShowOverrideForm] = React.useState(false);
  const [overrideReason, setOverrideReason] = React.useState("");

  const handleOverride = () => {
    if (onOverride && overrideReason.trim()) {
      onOverride(overrideReason);
      setShowOverrideForm(false);
      setOverrideReason("");
    }
  };

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          background: "none",
          border: "none",
          cursor: "pointer",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text)" }}>AI 판단</span>
          <SafetyBadge safety={outcomeLabel.safety_outcome} />
          <QualityBadge quality={outcomeLabel.quality_outcome} />
        </div>
        <svg 
          style={{ 
            width: "16px", 
            height: "16px", 
            color: "var(--text-muted)",
            transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s"
          }} 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isExpanded && (
        <div style={{ borderTop: "1px solid var(--border-light)", padding: "12px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>답변 유형</span>
            <ResponseTypeBadge response={outcomeLabel.response_outcome} />
          </div>

          {outcomeLabel.used_faq_keys.length > 0 && (
            <div style={{ marginBottom: "12px" }}>
              <span style={{ display: "block", fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>참고한 정보</span>
              <FaqKeysDisplay faqKeys={outcomeLabel.used_faq_keys} />
            </div>
          )}

          {outcomeLabel.rule_applied.length > 0 && (
            <div style={{ marginBottom: "12px" }}>
              <span style={{ display: "block", fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>적용된 규칙</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {outcomeLabel.rule_applied.map((rule, idx) => (
                  <span key={idx} className="badge badge-danger" style={{ fontSize: "10px" }}>
                    {rule}
                  </span>
                ))}
              </div>
            </div>
          )}

          {outcomeLabel.evidence_quote && (
            <div style={{ 
              background: "var(--bg)", 
              borderRadius: "var(--radius)", 
              padding: "8px 12px",
              marginBottom: "12px"
            }}>
              <span style={{ display: "block", fontSize: "10px", color: "var(--text-muted)", marginBottom: "4px" }}>근거</span>
              <p style={{ fontSize: "12px", fontStyle: "italic", color: "var(--text)" }}>"{outcomeLabel.evidence_quote}"</p>
            </div>
          )}

          {humanOverride?.applied && (
            <div style={{ 
              background: "rgba(99, 102, 241, 0.1)", 
              borderRadius: "var(--radius)", 
              padding: "8px 12px",
              marginBottom: "12px"
            }}>
              <span style={{ fontSize: "12px", color: "var(--primary)" }}>✓ 운영자 오버라이드 적용됨</span>
              <p style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "4px" }}>사유: {humanOverride.reason}</p>
            </div>
          )}

          {onOverride && !humanOverride?.applied && (
            <div style={{ borderTop: "1px solid var(--border-light)", paddingTop: "12px" }}>
              {!showOverrideForm ? (
                <button 
                  onClick={() => setShowOverrideForm(true)} 
                  style={{ 
                    fontSize: "12px", 
                    color: "var(--text-muted)", 
                    textDecoration: "underline",
                    background: "none",
                    border: "none",
                    cursor: "pointer"
                  }}
                >
                  이 판단이 맞지 않나요?
                </button>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <input
                    type="text"
                    value={overrideReason}
                    onChange={(e) => setOverrideReason(e.target.value)}
                    placeholder="오버라이드 사유"
                    className="input"
                  />
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button onClick={handleOverride} disabled={!overrideReason.trim()} className="btn btn-primary btn-sm">
                      저장
                    </button>
                    <button onClick={() => setShowOverrideForm(false)} className="btn btn-ghost btn-sm">
                      취소
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Compact Outcome Indicator
export function CompactOutcomeIndicator({ outcomeLabel }: { outcomeLabel?: OutcomeLabel | null }) {
  if (!outcomeLabel) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
      <SafetyBadge safety={outcomeLabel.safety_outcome} compact />
      <QualityBadge quality={outcomeLabel.quality_outcome} />
    </div>
  );
}

// Bulk Send Check
export function canBulkSend(outcomeLabel?: OutcomeLabel | null): boolean {
  if (!outcomeLabel) return true;
  if (outcomeLabel.safety_outcome === "HIGH_RISK") return false;
  if (outcomeLabel.quality_outcome === "REVIEW_REQUIRED") return false;
  return true;
}
