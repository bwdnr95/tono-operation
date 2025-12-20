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
  type StaffNotificationDTO,
  type StaffNotificationListResponse,
  OC_TOPIC_LABELS,
  OC_STATUS_LABELS,
} from "../api/staffNotifications";

// Priority 스타일 (새 디자인)
const PRIORITY_STYLES = {
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
// 개별 카드 컴포넌트
// ============================================================

interface NotificationCardProps {
  item: StaffNotificationDTO;
  onAction: (ocId: string, action: string) => Promise<void>;
  isLoading: boolean;
}

function NotificationCard({ item, onAction, isLoading }: NotificationCardProps) {
  const priorityStyle = PRIORITY_STYLES[item.priority] || PRIORITY_STYLES.pending;
  const topicLabel = OC_TOPIC_LABELS[item.topic] || item.topic;
  const statusLabel = OC_STATUS_LABELS[item.status] || item.status;

  return (
    <div className="card" style={{ marginBottom: "12px" }}>
      <div style={{ padding: "16px" }}>
        {/* 상단: Badge들 */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", flexWrap: "wrap" }}>
          <span className={`badge ${priorityStyle.badgeClass}`}>
            {priorityStyle.label}
          </span>
          <span className="badge badge-primary">
            {topicLabel}
          </span>
          {item.is_candidate_only && (
            <span className="badge" style={{ background: "rgba(168,85,247,0.1)", color: "#a855f7" }}>
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
            background: "rgba(16,185,129,0.05)",
            borderRadius: "var(--radius)",
            border: "1px solid rgba(16,185,129,0.2)"
          }}>
            <p style={{ fontSize: "11px", color: "var(--success)", marginBottom: "4px" }}>💬 게스트 메시지:</p>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", fontStyle: "italic" }}>
              "{item.resolution_evidence}"
            </p>
          </div>
        )}

        {/* Guest Info */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", fontSize: "12px", color: "var(--text-muted)" }}>
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
          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
            {statusLabel} · {item.created_at && new Date(item.created_at).toLocaleString("ko-KR")}
          </span>
          
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
  const [data, setData] = React.useState<StaffNotificationListResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);

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

  const items = data?.items || [];
  
  const immediateItems = items.filter((i) => i.priority === "immediate");
  const upcomingItems = items.filter((i) => i.priority === "upcoming");
  const pendingItems = items.filter((i) => i.priority === "pending");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Page Header */}
      <header className="page-header">
        <div className="page-header-content">
          <div>
            <h1 className="page-title">Staff Alerts</h1>
            <p className="page-subtitle">
              지금 처리해야 할 운영 약속입니다. 놓치면 CS 사고로 이어질 수 있습니다.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {data && (
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                기준일: {data.as_of}
              </span>
            )}
            <button
              onClick={() => void loadNotifications()}
              disabled={loading}
              className="btn btn-secondary"
            >
              {loading ? "로딩..." : "새로고침"}
            </button>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div style={{ padding: "16px 32px", display: "flex", gap: "16px" }}>
        <div className="stat-card" style={{ flex: 1 }}>
          <div className="stat-label">🔴 즉시</div>
          <div className="stat-value" style={{ color: "var(--danger)" }}>{immediateItems.length}</div>
        </div>
        <div className="stat-card" style={{ flex: 1 }}>
          <div className="stat-label">🟡 내일</div>
          <div className="stat-value" style={{ color: "var(--warning)" }}>{upcomingItems.length}</div>
        </div>
        <div className="stat-card" style={{ flex: 1 }}>
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
            {immediateItems.length > 0 && (
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
                    isLoading={actionLoading === item.oc_id}
                  />
                ))}
              </div>
            )}

            {/* 🟡 Upcoming */}
            {upcomingItems.length > 0 && (
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
                    isLoading={actionLoading === item.oc_id}
                  />
                ))}
              </div>
            )}

            {/* ⚪ Pending */}
            {pendingItems.length > 0 && (
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
                    isLoading={actionLoading === item.oc_id}
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
