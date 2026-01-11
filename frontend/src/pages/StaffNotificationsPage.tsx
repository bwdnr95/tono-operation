// src/pages/StaffNotificationsPage.tsx
/**
 * Staff Notification 페이지 (OC 기반)
 * 
 * Action Queue: 지금 처리해야 할 운영 약속
 * - 🔴 Immediate: 즉시 처리
 * - 🟡 Upcoming: D-1 준비
 * - ⚪ Pending: 대기
 */
import React from "react";
import {
  fetchStaffNotifications,
  markOCDone,
  confirmOCResolve,
  rejectOCResolve,
  confirmOCCandidate,
  rejectOCCandidate,
  changeOCPriority,
  type StaffNotificationDTO,
  type StaffNotificationListResponse,
  type OCPriority,
  OC_TOPIC_LABELS,
  OC_STATUS_LABELS,
} from "../api/staffNotifications";

// Priority 스타일 (새 디자인)
const PRIORITY_STYLES: Record<OCPriority, {
  label: string;
  badgeClass: string;
  headerColor: string;
}> = {
  immediate: {
    label: "즉시",
    badgeClass: "badge-danger",
    headerColor: "var(--danger)",
  },
  upcoming: {
    label: "내일",
    badgeClass: "badge-warning",
    headerColor: "var(--warning)",
  },
  pending: {
    label: "대기",
    badgeClass: "badge-default",
    headerColor: "var(--text-secondary)",
  },
};

// ============================================================
// Priority 선택 드롭다운
// ============================================================

interface PriorityDropdownProps {
  currentPriority: OCPriority;
  onSelect: (priority: OCPriority) => void;
  disabled?: boolean;
}

function PriorityDropdown({ currentPriority, onSelect, disabled }: PriorityDropdownProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);
  const priorityStyle = PRIORITY_STYLES[currentPriority] || PRIORITY_STYLES.pending;

  // 외부 클릭 시 닫기
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (priority: OCPriority) => {
    if (priority !== currentPriority) {
      onSelect(priority);
    }
    setIsOpen(false);
  };

  return (
    <div ref={dropdownRef} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`badge ${priorityStyle.badgeClass}`}
        style={{
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.6 : 1,
          border: "none",
          background: priorityStyle.badgeClass === "badge-danger" 
            ? "var(--danger-bg)" 
            : priorityStyle.badgeClass === "badge-warning"
            ? "var(--warning-bg)"
            : "var(--bg-secondary)",
          color: priorityStyle.badgeClass === "badge-danger"
            ? "var(--danger)"
            : priorityStyle.badgeClass === "badge-warning"
            ? "var(--warning)"
            : "var(--text-secondary)",
        }}
      >
        {priorityStyle.label} ▾
      </button>

      {isOpen && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            backgroundColor: "var(--surface)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-lg)",
            border: "1px solid var(--border)",
            overflow: "hidden",
            zIndex: 1000,
            minWidth: "80px",
          }}
        >
          {(["immediate", "upcoming", "pending"] as OCPriority[]).map((priority) => {
            const style = PRIORITY_STYLES[priority];
            const isSelected = priority === currentPriority;
            return (
              <button
                key={priority}
                onClick={() => handleSelect(priority)}
                style={{
                  display: "block",
                  width: "100%",
                  padding: "8px 12px",
                  border: "none",
                  background: isSelected ? "var(--bg-secondary)" : "transparent",
                  cursor: "pointer",
                  textAlign: "left",
                  fontSize: "13px",
                  color: style.badgeClass === "badge-danger"
                    ? "var(--danger)"
                    : style.badgeClass === "badge-warning"
                    ? "var(--warning)"
                    : "var(--text-secondary)",
                  fontWeight: isSelected ? 600 : 400,
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) e.currentTarget.style.background = "var(--bg-secondary)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = isSelected ? "var(--bg-secondary)" : "transparent";
                }}
              >
                {style.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================================
// 개별 카드 컴포넌트
// ============================================================

interface NotificationCardProps {
  item: StaffNotificationDTO;
  onAction: (ocId: string, action: string) => Promise<void>;
  onPriorityChange: (ocId: string, priority: OCPriority) => Promise<void>;
  isLoading: boolean;
  isHighlighted?: boolean;
}

function NotificationCard({ item, onAction, onPriorityChange, isLoading, isHighlighted }: NotificationCardProps) {
  const topicLabel = OC_TOPIC_LABELS[item.topic] || item.topic;
  const statusLabel = OC_STATUS_LABELS[item.status] || item.status;
  const cardRef = React.useRef<HTMLDivElement>(null);

  // 하이라이트된 항목으로 스크롤
  React.useEffect(() => {
    if (isHighlighted && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [isHighlighted]);

  return (
    <div 
      ref={cardRef}
      className="card" 
      style={{ 
        marginBottom: "12px",
        boxShadow: isHighlighted ? "0 0 0 2px var(--primary), 0 4px 12px rgba(99,102,241,0.2)" : undefined,
        transition: "box-shadow 0.3s ease",
      }}
    >
      <div style={{ padding: "16px" }}>
        {/* 상단: Badge들 */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", flexWrap: "wrap" }}>
          <PriorityDropdown
            currentPriority={item.priority}
            onSelect={(priority) => onPriorityChange(item.oc_id, priority)}
            disabled={isLoading}
          />
          <span className="badge badge-primary">
            {topicLabel}
          </span>
          {item.is_candidate_only && (
            <span className="badge" style={{ background: "var(--primary-bg)", color: "var(--primary)" }}>
              확정 필요
            </span>
          )}
          {item.status === "suggested_resolve" && (
            <span className="badge badge-success">
              해소 제안됨
            </span>
          )}
        </div>

        {/* Description */}
        <p style={{ fontWeight: 600, color: "var(--text)", marginBottom: "8px" }}>
          {item.description}
        </p>

        {/* Evidence Quote */}
        <p style={{ fontSize: "13px", color: "var(--text-secondary)", fontStyle: "italic", marginBottom: "12px" }}>
          "{item.evidence_quote}"
        </p>

        {/* Resolution Evidence */}
        {item.status === "suggested_resolve" && item.resolution_evidence && (
          <div style={{
            marginBottom: "12px",
            padding: "12px",
            background: "var(--success-bg)",
            borderRadius: "var(--radius)",
            border: "1px solid var(--success)"
          }}>
            <p style={{ fontSize: "11px", color: "var(--success)", marginBottom: "4px" }}>💬 게스트 메시지:</p>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", fontStyle: "italic" }}>
              "{item.resolution_evidence}"
            </p>
          </div>
        )}

        {/* Guest Info */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", fontSize: "12px", color: "var(--text-muted)" }}>
          {item.property_code && (
            <span style={{ fontWeight: 500, color: "var(--primary)" }}>{item.property_code}</span>
          )}
          {item.guest_name && (
            <span style={{ color: "var(--text)" }}>{item.guest_name}</span>
          )}
          {item.checkin_date && (
            <span>체크인 {item.checkin_date}</span>
          )}
          {item.target_date && (
            <span style={{ color: "var(--warning)" }}>목표일 {item.target_date}</span>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "16px", paddingTop: "12px", borderTop: "1px solid var(--border-light)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              {statusLabel} · {item.created_at && new Date(item.created_at).toLocaleString("ko-KR")}
            </span>
            {/* 에어비앤비 링크 버튼 */}
            {item.airbnb_thread_id && (
              <a
                href={`https://www.airbnb.co.kr/hosting/thread/${item.airbnb_thread_id}?thread_type=home_booking`}
                target="_blank"
                rel="noopener noreferrer"
                title="에어비앤비에서 대화 보기"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  padding: "4px 8px",
                  fontSize: "11px",
                  color: "#FF385C",
                  background: "var(--danger-bg)",
                  borderRadius: "4px",
                  textDecoration: "none",
                  fontWeight: 500,
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0C5.373 0 0 5.373 0 12c0 5.623 3.872 10.328 9.092 11.63a.75.75 0 0 0 .908-.657c.13-.738.324-1.526.578-2.344a.75.75 0 0 0-.263-.795C8.047 18.06 6.5 15.193 6.5 12c0-3.038 2.462-5.5 5.5-5.5s5.5 2.462 5.5 5.5c0 3.193-1.547 6.06-3.815 7.834a.75.75 0 0 0-.263.795c.254.818.448 1.606.578 2.344a.75.75 0 0 0 .908.657C20.128 22.328 24 17.623 24 12c0-6.627-5.373-12-12-12z"/>
                </svg>
                Airbnb
              </a>
            )}
          </div>
          
          <div style={{ display: "flex", gap: "8px" }}>
            {/* 후보 확정/거부 */}
            {item.is_candidate_only && (
              <>
                <button
                  onClick={() => onAction(item.oc_id, "confirm-candidate")}
                  disabled={isLoading}
                  className="btn btn-primary btn-sm"
                >
                  확정
                </button>
                <button
                  onClick={() => onAction(item.oc_id, "reject-candidate")}
                  disabled={isLoading}
                  className="btn btn-secondary btn-sm"
                >
                  거부
                </button>
              </>
            )}

            {/* suggested_resolve 확정/거부 */}
            {item.status === "suggested_resolve" && !item.is_candidate_only && (
              <>
                <button
                  onClick={() => onAction(item.oc_id, "confirm-resolve")}
                  disabled={isLoading}
                  className="btn btn-primary btn-sm"
                >
                  해소 확정
                </button>
                <button
                  onClick={() => onAction(item.oc_id, "reject-resolve")}
                  disabled={isLoading}
                  className="btn btn-secondary btn-sm"
                >
                  거부
                </button>
              </>
            )}

            {/* 일반 pending → 완료 처리 */}
            {item.status === "pending" && !item.is_candidate_only && (
              <button
                onClick={() => onAction(item.oc_id, "done")}
                disabled={isLoading}
                className="btn btn-primary btn-sm"
              >
                완료 처리
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 메인 페이지
// ============================================================

export const StaffNotificationsPage: React.FC = () => {
  const [searchParams, setSearchParams] = React.useState(() => new URLSearchParams(window.location.search));
  const urlOcId = searchParams.get("oc_id");
  
  const [data, setData] = React.useState<StaffNotificationListResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);
  const [highlightedOcId, setHighlightedOcId] = React.useState<string | null>(urlOcId);
  const [priorityFilter, setPriorityFilter] = React.useState<OCPriority | "all">("all");

  // URL 파라미터 처리 후 정리
  React.useEffect(() => {
    if (urlOcId) {
      setHighlightedOcId(urlOcId);
      // URL 정리
      window.history.replaceState({}, "", "/staff-notifications");
      // 3초 후 하이라이트 제거
      const timer = setTimeout(() => setHighlightedOcId(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [urlOcId]);

  const loadNotifications = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchStaffNotifications({ limit: 100 });
      setData(res);
    } catch (err: any) {
      console.error(err);
      setError(err?.message ?? "스태프 알림을 불러오는 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  const handleAction = async (ocId: string, action: string) => {
    setActionLoading(ocId);
    try {
      switch (action) {
        case "done":
          await markOCDone(ocId);
          break;
        case "confirm-resolve":
          await confirmOCResolve(ocId);
          break;
        case "reject-resolve":
          await rejectOCResolve(ocId);
          break;
        case "confirm-candidate":
          await confirmOCCandidate(ocId);
          break;
        case "reject-candidate":
          await rejectOCCandidate(ocId);
          break;
      }
      await loadNotifications();
    } catch (err: any) {
      console.error(err);
      alert(err?.message ?? "처리 중 오류가 발생했습니다.");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePriorityChange = async (ocId: string, priority: OCPriority) => {
    setActionLoading(ocId);
    try {
      await changeOCPriority(ocId, priority);
      await loadNotifications();
    } catch (err: any) {
      console.error(err);
      alert(err?.message ?? "우선순위 변경 중 오류가 발생했습니다.");
    } finally {
      setActionLoading(null);
    }
  };

  const items = data?.items || [];
  
  const immediateItems = items.filter((i) => i.priority === "immediate");
  const upcomingItems = items.filter((i) => i.priority === "upcoming");
  const pendingItems = items.filter((i) => i.priority === "pending");

  return (
    <div className="staff-alerts-page" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Page Header */}
      <header className="page-header">
        <div className="page-header-content">
          <div>
            <h1 className="page-title">Staff Alerts</h1>
            <p className="page-subtitle">
              지금 처리해야 할 운영 약속입니다.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {data && (
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                {data.as_of}
              </span>
            )}
            <button
              onClick={() => void loadNotifications()}
              disabled={loading}
              className="btn btn-secondary"
            >
              {loading ? "⟳" : "새로고침"}
            </button>
          </div>
        </div>
      </header>

      {/* Stats - 클릭하면 필터링 */}
      <div style={{ padding: "16px 32px", display: "flex", gap: "16px" }}>
        <div 
          className="stat-card" 
          style={{ 
            flex: 1, 
            cursor: "pointer",
            outline: priorityFilter === "immediate" ? "2px solid var(--danger)" : "none",
            background: priorityFilter === "immediate" ? "var(--danger-bg)" : undefined,
          }}
          onClick={() => setPriorityFilter(priorityFilter === "immediate" ? "all" : "immediate")}
        >
          <div className="stat-label">🔴 즉시</div>
          <div className="stat-value" style={{ color: "var(--danger)" }}>{immediateItems.length}</div>
        </div>
        <div 
          className="stat-card" 
          style={{ 
            flex: 1, 
            cursor: "pointer",
            outline: priorityFilter === "upcoming" ? "2px solid var(--warning)" : "none",
            background: priorityFilter === "upcoming" ? "var(--warning-bg)" : undefined,
          }}
          onClick={() => setPriorityFilter(priorityFilter === "upcoming" ? "all" : "upcoming")}
        >
          <div className="stat-label">🟡 내일</div>
          <div className="stat-value" style={{ color: "var(--warning)" }}>{upcomingItems.length}</div>
        </div>
        <div 
          className="stat-card" 
          style={{ 
            flex: 1, 
            cursor: "pointer",
            outline: priorityFilter === "pending" ? "2px solid var(--text-secondary)" : "none",
            background: priorityFilter === "pending" ? "var(--bg-secondary)" : undefined,
          }}
          onClick={() => setPriorityFilter(priorityFilter === "pending" ? "all" : "pending")}
        >
          <div className="stat-label">⚪ 대기</div>
          <div className="stat-value">{pendingItems.length}</div>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 32px 32px" }}>
        {loading && items.length === 0 ? (
          <div className="empty-state">
            <div className="loading-spinner" />
          </div>
        ) : error ? (
          <div className="card" style={{ padding: "24px", color: "var(--danger)" }}>
            {error}
          </div>
        ) : items.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">✅</div>
              <div className="empty-state-title">처리할 알림이 없습니다</div>
              <div className="empty-state-text">모든 약속이 정상적으로 이행되었습니다 👍</div>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            {/* 🔴 Immediate */}
            {(priorityFilter === "all" || priorityFilter === "immediate") && immediateItems.length > 0 && (
              <div>
                <h2 style={{ fontSize: "14px", fontWeight: 600, color: "var(--danger)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
                  🔴 즉시 처리 필요
                  <span style={{ fontSize: "12px", fontWeight: 400, color: "var(--text-muted)" }}>({immediateItems.length})</span>
                </h2>
                {immediateItems.map((item) => (
                  <NotificationCard
                    key={item.oc_id}
                    item={item}
                    onAction={handleAction}
                    onPriorityChange={handlePriorityChange}
                    isLoading={actionLoading === item.oc_id}
                    isHighlighted={highlightedOcId === item.oc_id}
                  />
                ))}
              </div>
            )}

            {/* 🟡 Upcoming */}
            {(priorityFilter === "all" || priorityFilter === "upcoming") && upcomingItems.length > 0 && (
              <div>
                <h2 style={{ fontSize: "14px", fontWeight: 600, color: "var(--warning)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
                  🟡 내일 준비 필요
                  <span style={{ fontSize: "12px", fontWeight: 400, color: "var(--text-muted)" }}>({upcomingItems.length})</span>
                </h2>
                {upcomingItems.map((item) => (
                  <NotificationCard
                    key={item.oc_id}
                    item={item}
                    onAction={handleAction}
                    onPriorityChange={handlePriorityChange}
                    isLoading={actionLoading === item.oc_id}
                    isHighlighted={highlightedOcId === item.oc_id}
                  />
                ))}
              </div>
            )}

            {/* ⚪ Pending */}
            {(priorityFilter === "all" || priorityFilter === "pending") && pendingItems.length > 0 && (
              <div>
                <h2 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
                  ⚪ 대기
                  <span style={{ fontSize: "12px", fontWeight: 400, color: "var(--text-muted)" }}>({pendingItems.length})</span>
                </h2>
                {pendingItems.map((item) => (
                  <NotificationCard
                    key={item.oc_id}
                    item={item}
                    onAction={handleAction}
                    onPriorityChange={handlePriorityChange}
                    isLoading={actionLoading === item.oc_id}
                    isHighlighted={highlightedOcId === item.oc_id}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
