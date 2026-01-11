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
import { SkeletonConversationList } from "../components/ui/Skeleton";

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
  // 다크모드 지원 CSS 변수 사용
  const colorStyles: Record<string, { bg: string; border: string; text: string }> = {
    default: { bg: "var(--surface)", border: "var(--border)", text: "var(--text)" },
    warning: { bg: "var(--warning-bg)", border: "var(--warning)", text: "var(--warning)" },
    danger: { bg: "var(--danger-bg)", border: "var(--danger)", text: "var(--danger)" },
    success: { bg: "var(--success-bg)", border: "var(--success)", text: "var(--success)" },
  };
  const style = colorStyles[color];

  return (
    <div
      onClick={onClick}
      style={{
        background: style.bg,
        border: `1px solid ${style.border}`,
        borderRadius: "var(--radius-lg)",
        padding: "16px 20px",
        cursor: onClick ? "pointer" : "default",
        transition: "transform 0.15s, box-shadow 0.15s",
        minWidth: "140px",
      }}
      onMouseEnter={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = "translateY(-2px)";
          e.currentTarget.style.boxShadow = "var(--shadow-md)";
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
  onClick?: () => void;
}

function PendingReservationItem({ item, onClick }: PendingReservationItemProps) {
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
      onClick={onClick}
      className="conversation-item"
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
          <div style={{ fontSize: "14px", fontWeight: "600", color: "var(--success)", marginBottom: "4px" }}>
            {formatCurrency(item.expected_payout)}
          </div>
          <div
            style={{
              fontSize: "12px",
              fontWeight: "600",
              color: isUrgent ? "var(--danger)" : isExpiring ? "var(--warning)" : "var(--text-secondary)",
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
              background: "var(--danger)",
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
  const hours = item.hours_since_last_message ?? 0;
  
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
              background: hours >= 2 ? "var(--danger-bg)" : hours >= 1 ? "var(--warning-bg)" : "var(--success-bg)",
              color: hours >= 2 ? "var(--danger)" : hours >= 1 ? "var(--warning)" : "var(--success)",
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

// Topic 한글 라벨
const TOPIC_LABELS: Record<string, string> = {
  early_checkin: "얼리체크인",
  late_checkout: "레이트체크아웃",
  follow_up: "후속 안내",
  facility_issue: "시설 문제",
  visit_schedule: "방문 일정",
  amenity_request: "어메니티 요청",
  refund: "환불",
  payment: "결제",
  compensation: "보상",
};

function StaffAlertItem({ item, onClick }: StaffAlertItemProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const topicLabel = TOPIC_LABELS[item.topic] || item.topic;

  return (
    <div onClick={onClick} className="conversation-item">
      <div className="conversation-avatar" style={{ background: "var(--danger-bg)", color: "var(--danger)" }}>
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
          [{topicLabel}] {item.description}
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

  // ===== Auto Refresh (5분마다) =====
  useEffect(() => {
    const REFRESH_INTERVAL = 5 * 60 * 1000; // 5분
    
    const interval = setInterval(() => {
      if (!loading) {
        fetchData();
      }
    }, REFRESH_INTERVAL);
    
    return () => clearInterval(interval);
  }, [loading, fetchData]);

  // ===== 탭 포커스 시 새로고침 =====
  useEffect(() => {
    let lastRefresh = Date.now();
    const MIN_REFRESH_GAP = 30 * 1000; // 최소 30초 간격
    
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        const now = Date.now();
        if (now - lastRefresh > MIN_REFRESH_GAP && !loading) {
          lastRefresh = now;
          fetchData();
        }
      }
    };
    
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [loading, fetchData]);

  // Handlers
  const handleUnansweredClick = (item: UnansweredMessageDTO) => {
    navigate(`/inbox?conversation_id=${item.conversation_id}`);
  };

  const handleStaffAlertClick = (item: StaffAlertDTO) => {
    navigate(`/staff-notifications?oc_id=${item.oc_id}`);
  };

  // Render
  return (
    <PageLayout>
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Page Header - InboxPage 스타일 */}
        <header className="page-header dashboard-header">
          <div className="page-header-content">
            <div>
              <h1 className="page-title">대시보드</h1>
              <p className="page-subtitle">운영 현황을 한눈에 확인하세요</p>
            </div>
            <div className="dashboard-header-actions" style={{ display: "flex", gap: "8px" }}>
              <button onClick={fetchData} disabled={loading} className="btn btn-secondary dashboard-refresh-btn">
                {loading ? "⟳" : "↻"}
              </button>
            </div>
          </div>
        </header>

        {/* Error */}
        {error && (
          <div
            style={{
              background: "var(--danger-bg)",
              border: "1px solid var(--danger)",
              borderRadius: "var(--radius)",
              padding: "12px 16px",
              margin: "0 32px 16px",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        )}

        {/* Summary Cards */}
        {summary && (
          <div
            className="dashboard-summary-cards"
            style={{
              display: "flex",
              gap: "16px",
              padding: "24px 32px",
              overflowX: "auto",
            }}
          >
            <SummaryCard
              icon="📩"
              label="예약 요청"
              count={summary.pending_reservations_count}
              color={summary.pending_reservations_count > 0 ? "warning" : "default"}
              onClick={() => navigate("/booking-requests")}
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
        <div className="dashboard-main-content" style={{ flex: 1, padding: "0 32px 32px", display: "flex", flexDirection: "column", gap: "20px", minHeight: 0 }}>
          
          {/* 미응답 메시지 - 전체 너비 */}
          <div className="card dashboard-card" style={{ flex: 1, minHeight: "200px", display: "flex", flexDirection: "column" }}>
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
                <SkeletonConversationList count={4} />
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
          <div className="dashboard-grid-2col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", flex: 1, minHeight: "200px" }}>
            {/* 예약 요청 */}
            <div className="card dashboard-card" style={{ display: "flex", flexDirection: "column" }}>
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
                <button
                  onClick={() => navigate("/booking-requests")}
                  className="btn btn-ghost btn-sm"
                >
                  전체 보기 →
                </button>
              </div>
              <div style={{ flex: 1, overflowY: "auto" }}>
                {loading ? (
                  <SkeletonConversationList count={3} />
                ) : pendingReservations.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">✓</div>
                    <div className="empty-state-title">대기 중인 예약 요청이 없습니다</div>
                  </div>
                ) : (
                  pendingReservations.map((item) => (
                    <PendingReservationItem 
                      key={item.id} 
                      item={item} 
                      onClick={() => navigate(`/booking-requests?id=${item.id}`)}
                    />
                  ))
                )}
              </div>
            </div>

            {/* Staff Alerts */}
            <div className="card dashboard-card" style={{ display: "flex", flexDirection: "column" }}>
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
                  <SkeletonConversationList count={3} />
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
