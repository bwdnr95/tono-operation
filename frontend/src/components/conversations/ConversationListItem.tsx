import type { ConversationListItemDTO, SafetyStatus } from "../../types/conversations";

function formatDate(v: string | null | undefined) {
  if (!v) return null;
  try {
    return new Date(v).toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  } catch {
    return v;
  }
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

/**
 * 기능(라벨)은 유지하되, "운영 SaaS 톤"을 위해 색상 난립을 줄인다.
 * - 대부분: 중립 pill (stroke + muted)
 * - attention: accent outline
 */
type Tone = "neutral" | "attention";

const STATUS_CONFIG: Record<string, { label: string; tone: Tone }> = {
  new: { label: "신규", tone: "neutral" },
  open: { label: "대기", tone: "neutral" },
  pending: { label: "대기", tone: "neutral" },
  needs_review: { label: "검토", tone: "attention" },
  ready_to_send: { label: "발송준비", tone: "neutral" },
  sent: { label: "완료", tone: "neutral" },
  complete: { label: "완료", tone: "neutral" },
  blocked: { label: "차단", tone: "attention" },
};

const SAFETY_CONFIG: Record<SafetyStatus, { label: string; tone: Tone }> = {
  pass: { label: "안전", tone: "neutral" },
  review: { label: "검토", tone: "attention" },
  block: { label: "차단", tone: "attention" },
};

function pillClass(tone: Tone) {
  // TONO 스타일: 다색 배경 금지 → outline 중심
  return tone === "attention"
    ? "border-dark-accent text-dark-text"
    : "border-dark-border text-dark-muted";
}

function safetyDotClass(tone: Tone) {
  // 점(dot)은 기능적으로 유지하되, 컬러 난립을 막기 위해 accent/중립만 사용
  // pass: 중립(투명) / review, block: accent
  return tone === "attention" ? "bg-dark-accent" : "bg-transparent";
}

interface Props {
  item: ConversationListItemDTO;
  selected: boolean;
  onClick: () => void;
}

export function ConversationListItem({ item, selected, onClick }: Props) {
  const statusCfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.new;
  const safetyCfg = SAFETY_CONFIG[item.safety_status];

  const showAccentBar = selected || statusCfg.tone === "attention" || safetyCfg.tone === "attention";

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "group relative flex w-full text-left",
        "border-b border-dark-border",
      ].join(" ")}
    >
      {/* Left accent bar: 선택/주의만 표시 (운영 SaaS 문법) */}
      <div className={`w-[3px] ${showAccentBar ? "bg-dark-accent" : "bg-transparent"}`} />

      <div
        className={[
          "flex flex-1 items-start gap-3 px-4 py-3",
          "transition-colors",
          selected ? "bg-dark-surface" : "hover:bg-dark-surface",
        ].join(" ")}
      >
        {/* Avatar (기능 유지) */}
        <div className="relative mt-0.5">
          <div
            className={[
              "flex h-10 w-10 items-center justify-center rounded-full",
              "border border-dark-border bg-dark-card",
              "text-sm font-bold text-dark-text",
            ].join(" ")}
            aria-label="Guest avatar"
          >
            {item.guest_name?.charAt(0) || "?"}
          </div>

          {/* Safety dot (기능 유지: 점 + title) */}
          <span
            className={[
              "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full",
              "border-2 border-dark-bg",
              safetyDotClass(safetyCfg.tone),
            ].join(" ")}
            title={`Safety: ${item.safety_status}`}
          />
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <span className="truncate font-medium text-dark-text">
              {item.guest_name || "게스트"}
            </span>

            {/* Status pill (기능 유지: 상태 표기) */}
            <span
              className={[
                "shrink-0 rounded-full border px-2 py-0.5",
                "text-[10px] font-medium",
                pillClass(statusCfg.tone),
              ].join(" ")}
            >
              {statusCfg.label}
            </span>
          </div>

          {/* Property code */}
          {item.property_code && (
            <div className="mt-0.5 text-[10px] font-medium text-dark-accent">
              {item.property_code}
            </div>
          )}

          {/* Check-in/out (기능 유지) */}
          {item.checkin_date && item.checkout_date && (
            <div className="mt-1 text-xs text-dark-muted">
              {formatDate(item.checkin_date)} → {formatDate(item.checkout_date)}
            </div>
          )}

          {/* Updated time (기능 유지) */}
          <div className="mt-1 text-[11px] text-dark-muted/70">
            {formatTime(item.updated_at)}
          </div>

          {/* Safety label (기능 추가가 아니라 “표기 강화”: 원하면 제거 가능)
              - 점만으로 불안하면 운영툴에서는 라벨이 오히려 신뢰감 올라감
           */}
          <div className="mt-2 flex items-center gap-2">
            <span
              className={[
                "rounded-full border px-2 py-0.5",
                "text-[10px] font-medium",
                pillClass(safetyCfg.tone),
              ].join(" ")}
              title={`Safety label: ${item.safety_status}`}
            >
              {safetyCfg.label}
            </span>
          </div>
        </div>
      </div>
    </button>
  );
}
