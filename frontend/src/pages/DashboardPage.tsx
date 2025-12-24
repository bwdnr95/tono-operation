// src/pages/DashboardPage.tsx
/**
 * Dashboard Page
 * 
 * 운영 현황 한눈에 보기:
 * - 미응답 메시지 (전체 너비)
 * - 예약 요청 + Staff Alerts (50:50)
 * - 오늘 체크인/체크아웃
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { PageLayout } from "../layout/PageLayout";

import {
  getDashboardSummary,
  getPendingReservations,
  getUnansweredMessages,
  getStaffAlerts,
} from "../api/dashboard";

import type {
  DashboardSummaryDTO,
  PendingReservationDTO,
  UnansweredMessageDTO,
  StaffAlertDTO,
} from "../types/dashboard";

// ============================================================
// Summary Card Component
// ============================================================

interface SummaryCardProps {
  icon: string;
  label: string;
  count: number;
  color?: "default" | "warning" | "danger" | "success";
  onClick?: () => void;
}

function SummaryCard({ icon, label, count, color = "default", onClick }: SummaryCardProps) {
  const colorStyles: Record<string, { bg: string; border: string; text: string }> = {
    default: { bg: "var(--bg-primary)", border: "var(--border-color)", text: "var(--text-primary)" },
    warning: { bg: "#fffbeb", border: "#fbbf24", text: "#b45309" },
    danger: { bg: "#fef2f2", border: "#ef4444", text: "#dc2626" },
    success: { bg: "#f0fdf4", border: "#22c55e", text: "#16a34a" },
  };
  const style = colorStyles[color];

  return (
    <div
      onClick={onClick}
      style={{
        background: style.bg,
        border: `1px solid ${style.border}`,
        borderRadius: "12px",
        padding: "16px 20px",
        cursor: onClick ? "pointer" : "default",
        transition: "transform 0.15s, box-shadow 0.15s",
        minWidth: "140px",
      }}
      onMouseEnter={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = "translateY(-2px)";
          e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.1)";
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <span style={{ fontSize: "24px" }}>{icon}</span>
        <div>
          <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "2px" }}>
            {label}
          </div>
          <div style={{ fontSize: "24px", fontWeight: "700", color: style.text }}>
            {count}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Pending Reservation Item
// ============================================================

interface PendingReservationItemProps {
  item: PendingReservationDTO;
}

function PendingReservationItem({ item }: PendingReservationItemProps) {
  const remainingHours = item.remaining_hours ?? 0;
  const isUrgent = remainingHours <= 6;
  const isExpiring = remainingHours <= 12 && remainingHours > 6;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const formatCurrency = (amount: number | null) => {
    if (!amount) return "-";
    return `₩${amount.toLocaleString()}`;
  };

  return (
    <div
      className="conversation-item"
      style={{
        background: isUrgent ? "#fef2f2" : isExpiring ? "#fffbeb" : "transparent",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", width: "100%" }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
            <span style={{ fontWeight: "600" }}>{item.guest_name || "게스트"}</span>
            {item.property_code && (
              <span className="badge badge-primary" style={{ fontSize: "10px" }}>
                {item.property_code}
              </span>
            )}
            {item.guest_verified && (
              <span className="badge badge-success" style={{ fontSize: "10px" }}>인증됨</span>
            )}
          </div>
          <div style={{ fontSize: "13px", color: "var(--text-muted)", marginBottom: "4px" }}>
            {formatDate(item.checkin_date)} ~ {formatDate(item.checkout_date)} · {item.nights || 0}박
          </div>
          {item.guest_message && (
            <div style={{ fontSize: "12px", color: "var(--text-secondary)", fontStyle: "italic" }}>
              "{item.guest_message.slice(0, 40)}..."
            </div>
          )}
        </div>
        <div style={{ textAlign: "right", marginLeft: "12px" }}>
          <div style={{ fontSize: "14px", fontWeight: "600", color: "#16a34a", marginBottom: "4px" }}>
            {formatCurrency(item.expected_payout)}
          </div>
          <div
            style={{
              fontSize: "12px",
              fontWeight: "600",
              color: isUrgent ? "#dc2626" : isExpiring ? "#f59e0b" : "#6b7280",
              marginBottom: "6px",
            }}
          >
            {remainingHours > 0 ? `${Math.round(remainingHours)}시간 남음` : "만료됨"}
          </div>
          <a
            href={item.action_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="btn btn-sm"
            style={{
              background: "#ff385c",
              color: "white",
              padding: "4px 10px",
              fontSize: "11px",
            }}
          >
            처리하기
          </a>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Unanswered Message Item
// ============================================================

interface UnansweredMessageItemProps {
  item: UnansweredMessageDTO;
  onClick: () => void;
}

function UnansweredMessageItem({ item, onClick }: UnansweredMessageItemProps) {
  const hours = item.hours_since_last_message;
  
  const formatTime = (h: number) => {
    if (h < 1) return "방금 전";
    if (h < 24) return `${Math.round(h)}시간 전`;
    return `${Math.round(h / 24)}일 전`;
  };
  
  return (
    <div onClick={onClick} className="conversation-item">
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
        <div className="conversation-preview">
          {item.last_message_preview || "메시지 없음"}
        </div>
        <div className="conversation-meta">
          <span
            className="badge"
            style={{
              background: hours >= 2 ? "#fef2f2" : hours >= 1 ? "#fffbeb" : "#f0fdf4",
              color: hours >= 2 ? "#dc2626" : hours >= 1 ? "#b45309" : "#16a34a",
            }}
          >
            {formatTime(hours)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Staff Alert Item
// ============================================================

interface StaffAlertItemProps {
  item: StaffAlertDTO;
  onClick: () => void;
}

function StaffAlertItem({ item, onClick }: StaffAlertItemProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <div onClick={onClick} className="conversation-item">
      <div className="conversation-avatar" style={{ background: "#fef2f2", color: "#dc2626" }}>
        !
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
        <div className="conversation-preview">
          {item.alert_reason}
        </div>
        <div className="conversation-meta">
          <span className="badge badge-warning">
            {formatDate(item.target_date)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Main Component
// ============================================================

export function DashboardPage() {
  const navigate = useNavigate();

  // State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummaryDTO | null>(null);
  const [pendingReservations, setPendingReservations] = useState<PendingReservationDTO[]>([]);
  const [unansweredMessages, setUnansweredMessages] = useState<UnansweredMessageDTO[]>([]);
  const [staffAlerts, setStaffAlerts] = useState<StaffAlertDTO[]>([]);

  // Fetch Data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [summaryRes, pendingRes, unansweredRes, alertsRes] = await Promise.all([
        getDashboardSummary(),
        getPendingReservations(),
        getUnansweredMessages(),
        getStaffAlerts(),
      ]);

      setSummary(summaryRes);
      setPendingReservations(pendingRes.items);
      setUnansweredMessages(unansweredRes.items);
      setStaffAlerts(alertsRes.items);
    } catch (e: any) {
      setError(e?.message || "데이터 로딩 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handlers
  const handleUnansweredClick = (item: UnansweredMessageDTO) => {
    navigate(`/inbox?conversation_id=${item.conversation_id}`);
  };

  const handleStaffAlertClick = (item: StaffAlertDTO) => {
    navigate(`/inbox?conversation_id=${item.conversation_id}`);
  };

  // Render
  return (
    <PageLayout>
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Page Header - InboxPage 스타일 */}
        <header className="page-header">
          <div className="page-header-content">
            <div>
              <h1 className="page-title">대시보드</h1>
              <p className="page-subtitle">운영 현황을 한눈에 확인하세요</p>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button onClick={fetchData} disabled={loading} className="btn btn-secondary">
                {loading ? "로딩..." : "새로고침"}
              </button>
            </div>
          </div>
        </header>

        {/* Error */}
        {error && (
          <div
            style={{
              background: "#fef2f2",
              border: "1px solid #fca5a5",
              borderRadius: "8px",
              padding: "12px 16px",
              margin: "0 32px 16px",
              color: "#dc2626",
            }}
          >
            {error}
          </div>
        )}

        {/* Summary Cards */}
        {summary && (
          <div
            style={{
              display: "flex",
              gap: "16px",
              padding: "0 32px 24px",
              overflowX: "auto",
            }}
          >
            <SummaryCard
              icon="📩"
              label="예약 요청"
              count={summary.pending_reservations_count}
              color={summary.pending_reservations_count > 0 ? "warning" : "default"}
            />
            <SummaryCard
              icon="💬"
              label="미응답 메시지"
              count={summary.unanswered_messages_count}
              color={summary.unanswered_messages_count > 0 ? "danger" : "default"}
              onClick={() => navigate("/inbox?is_read=false")}
            />
            <SummaryCard
              icon="🔔"
              label="Staff Alerts"
              count={summary.staff_alerts_count}
              color={summary.staff_alerts_count > 0 ? "danger" : "default"}
              onClick={() => navigate("/staff-notifications")}
            />
            <SummaryCard
              icon="🏠"
              label="오늘 체크인"
              count={summary.today_checkins_count}
              color="success"
            />
            <SummaryCard
              icon="🚪"
              label="오늘 체크아웃"
              count={summary.today_checkouts_count}
              color="default"
            />
          </div>
        )}

        {/* Main Content - InboxPage 스타일 레이아웃 */}
        <div style={{ flex: 1, padding: "0 32px 32px", display: "flex", flexDirection: "column", gap: "20px", minHeight: 0 }}>
          
          {/* 미응답 메시지 - 전체 너비 */}
          <div className="card" style={{ flex: 1, minHeight: "200px", display: "flex", flexDirection: "column" }}>
            <div className="card-header">
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span>💬</span>
                <span className="card-title">미응답 메시지</span>
                {unansweredMessages.length > 0 && (
                  <span className="badge badge-danger">
                    {summary?.unanswered_messages_count || unansweredMessages.length}
                  </span>
                )}
              </div>
              <button
                onClick={() => navigate("/inbox?is_read=false")}
                className="btn btn-ghost btn-sm"
              >
                전체 보기 →
              </button>
            </div>
            <div style={{ flex: 1, overflowY: "auto" }}>
              {loading ? (
                <div className="empty-state">
                  <div className="loading-spinner" />
                </div>
              ) : unansweredMessages.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon">✓</div>
                  <div className="empty-state-title">미응답 메시지가 없습니다</div>
                </div>
              ) : (
                unansweredMessages.map((item) => (
                  <UnansweredMessageItem
                    key={item.conversation_id}
                    item={item}
                    onClick={() => handleUnansweredClick(item)}
                  />
                ))
              )}
            </div>
          </div>

          {/* 예약 요청 + Staff Alerts - 50:50 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", flex: 1, minHeight: "200px" }}>
            {/* 예약 요청 */}
            <div className="card" style={{ display: "flex", flexDirection: "column" }}>
              <div className="card-header">
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span>📩</span>
                  <span className="card-title">예약 요청</span>
                  {pendingReservations.length > 0 && (
                    <span className="badge badge-warning">
                      {pendingReservations.length}
                    </span>
                  )}
                </div>
              </div>
              <div style={{ flex: 1, overflowY: "auto" }}>
                {loading ? (
                  <div className="empty-state">
                    <div className="loading-spinner" />
                  </div>
                ) : pendingReservations.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">✓</div>
                    <div className="empty-state-title">대기 중인 예약 요청이 없습니다</div>
                  </div>
                ) : (
                  pendingReservations.map((item) => (
                    <PendingReservationItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>

            {/* Staff Alerts */}
            <div className="card" style={{ display: "flex", flexDirection: "column" }}>
              <div className="card-header">
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span>🔔</span>
                  <span className="card-title">Staff Alerts</span>
                  {staffAlerts.length > 0 && (
                    <span className="badge badge-danger">
                      {staffAlerts.length}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => navigate("/staff-notifications")}
                  className="btn btn-ghost btn-sm"
                >
                  전체 보기 →
                </button>
              </div>
              <div style={{ flex: 1, overflowY: "auto" }}>
                {loading ? (
                  <div className="empty-state">
                    <div className="loading-spinner" />
                  </div>
                ) : staffAlerts.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">✓</div>
                    <div className="empty-state-title">Staff Alerts가 없습니다</div>
                  </div>
                ) : (
                  staffAlerts.map((item) => (
                    <StaffAlertItem
                      key={item.oc_id}
                      item={item}
                      onClick={() => handleStaffAlertClick(item)}
                    />
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
