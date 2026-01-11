// src/pages/DashboardPage.tsx
/**
 * Dashboard Page - v2 Redesign
 * 
 * 레퍼런스: Dark Glassmorphism SaaS Style
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
// Design Tokens (인라인 사용)
// ============================================================
const tokens = {
  // Backgrounds
  bgBase: '#08080c',
  bgElevated: '#0f0f14',
  bgSurface: '#16161e',
  bgSurfaceHover: '#1c1c26',
  
  // Glass
  glassBg: 'rgba(255, 255, 255, 0.03)',
  glassBorder: 'rgba(255, 255, 255, 0.06)',
  glassBorderHover: 'rgba(255, 255, 255, 0.1)',
  
  // Text
  textPrimary: '#ffffff',
  textSecondary: '#a1a1aa',
  textMuted: '#71717a',
  
  // Accent
  accent: '#8b5cf6',
  accentGradient: 'linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%)',
  accentMuted: 'rgba(139, 92, 246, 0.15)',
  
  // Status
  success: '#22c55e',
  successMuted: 'rgba(34, 197, 94, 0.15)',
  warning: '#f59e0b',
  warningMuted: 'rgba(245, 158, 11, 0.15)',
  danger: '#ef4444',
  dangerMuted: 'rgba(239, 68, 68, 0.15)',
  
  // Shadows
  shadowMd: '0 4px 12px rgba(0, 0, 0, 0.4)',
  shadowLg: '0 8px 24px rgba(0, 0, 0, 0.5)',
  shadowAccent: '0 4px 20px rgba(139, 92, 246, 0.3)',
  
  // Radius
  radiusMd: '8px',
  radiusLg: '12px',
  radiusXl: '16px',
};

// ============================================================
// Summary Card Component (Redesigned)
// ============================================================
interface SummaryCardProps {
  icon: string;
  label: string;
  count: number;
  color?: "default" | "warning" | "danger" | "success";
  onClick?: () => void;
}

function SummaryCard({ icon, label, count, color = "default", onClick }: SummaryCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  
  const colorMap = {
    default: { bg: tokens.bgSurface, border: tokens.glassBorder, accent: tokens.textPrimary },
    warning: { bg: tokens.warningMuted, border: 'rgba(245, 158, 11, 0.3)', accent: tokens.warning },
    danger: { bg: tokens.dangerMuted, border: 'rgba(239, 68, 68, 0.3)', accent: tokens.danger },
    success: { bg: tokens.successMuted, border: 'rgba(34, 197, 94, 0.3)', accent: tokens.success },
  };
  
  const style = colorMap[color];

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        background: style.bg,
        border: `1px solid ${isHovered ? tokens.glassBorderHover : style.border}`,
        borderRadius: tokens.radiusLg,
        padding: '20px 24px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
        transform: isHovered && onClick ? 'translateY(-2px)' : 'none',
        boxShadow: isHovered ? tokens.shadowLg : tokens.shadowMd,
        minWidth: '160px',
        flex: '1 1 0',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{
          width: '44px',
          height: '44px',
          borderRadius: tokens.radiusMd,
          background: tokens.glassBg,
          border: `1px solid ${tokens.glassBorder}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '22px',
        }}>
          {icon}
        </div>
        <div>
          <div style={{ 
            fontSize: '13px', 
            color: tokens.textSecondary, 
            marginBottom: '4px',
            fontWeight: 500,
          }}>
            {label}
          </div>
          <div style={{ 
            fontSize: '28px', 
            fontWeight: 700, 
            color: style.accent,
            letterSpacing: '-0.02em',
          }}>
            {count}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Card Component (Glass Style)
// ============================================================
interface CardProps {
  title: string;
  icon: string;
  badge?: number;
  badgeColor?: 'danger' | 'warning' | 'success';
  onViewAll?: () => void;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

function Card({ title, icon, badge, badgeColor = 'danger', onViewAll, children, style }: CardProps) {
  const badgeColors = {
    danger: { bg: tokens.danger, text: '#fff' },
    warning: { bg: tokens.warning, text: '#000' },
    success: { bg: tokens.success, text: '#fff' },
  };
  
  return (
    <div style={{
      background: tokens.bgSurface,
      border: `1px solid ${tokens.glassBorder}`,
      borderRadius: tokens.radiusXl,
      boxShadow: tokens.shadowMd,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      ...style,
    }}>
      {/* Card Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: `1px solid ${tokens.glassBorder}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '18px' }}>{icon}</span>
          <span style={{ 
            fontSize: '15px', 
            fontWeight: 600, 
            color: tokens.textPrimary,
          }}>
            {title}
          </span>
          {badge !== undefined && badge > 0 && (
            <span style={{
              background: badgeColors[badgeColor].bg,
              color: badgeColors[badgeColor].text,
              padding: '3px 10px',
              borderRadius: '20px',
              fontSize: '11px',
              fontWeight: 700,
            }}>
              {badge}
            </span>
          )}
        </div>
        {onViewAll && (
          <button
            onClick={onViewAll}
            style={{
              background: 'transparent',
              border: 'none',
              color: tokens.textMuted,
              fontSize: '13px',
              cursor: 'pointer',
              padding: '6px 12px',
              borderRadius: tokens.radiusMd,
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = tokens.glassBg;
              e.currentTarget.style.color = tokens.textPrimary;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = tokens.textMuted;
            }}
          >
            전체 보기 →
          </button>
        )}
      </div>
      
      {/* Card Body */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {children}
      </div>
    </div>
  );
}

// ============================================================
// List Item Component
// ============================================================
interface ListItemProps {
  avatar?: string;
  title: string;
  subtitle?: string;
  meta?: string;
  metaColor?: string;
  badge?: string;
  badgeColor?: 'primary' | 'success' | 'warning' | 'danger';
  rightContent?: React.ReactNode;
  onClick?: () => void;
  statusBar?: 'primary' | 'success' | 'warning' | 'danger';
}

function ListItem({ 
  avatar, 
  title, 
  subtitle, 
  meta, 
  metaColor,
  badge, 
  badgeColor = 'primary',
  rightContent,
  onClick,
  statusBar,
}: ListItemProps) {
  const [isHovered, setIsHovered] = useState(false);
  
  const badgeColors = {
    primary: { bg: tokens.accentMuted, text: tokens.accent },
    success: { bg: tokens.successMuted, text: tokens.success },
    warning: { bg: tokens.warningMuted, text: tokens.warning },
    danger: { bg: tokens.dangerMuted, text: tokens.danger },
  };
  
  const statusColors = {
    primary: tokens.accent,
    success: tokens.success,
    warning: tokens.warning,
    danger: tokens.danger,
  };
  
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        padding: '14px 20px',
        cursor: onClick ? 'pointer' : 'default',
        background: isHovered ? tokens.glassBg : 'transparent',
        borderBottom: `1px solid ${tokens.glassBorder}`,
        transition: 'background 0.15s',
        display: 'flex',
        alignItems: 'center',
        gap: '14px',
      }}
    >
      {/* Status Bar */}
      {statusBar && (
        <div style={{
          width: '3px',
          height: '36px',
          borderRadius: '2px',
          background: statusColors[statusBar],
          flexShrink: 0,
        }} />
      )}
      
      {/* Avatar */}
      {avatar && (
        <div style={{
          width: '40px',
          height: '40px',
          borderRadius: tokens.radiusMd,
          background: tokens.accentGradient,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '14px',
          fontWeight: 600,
          color: '#fff',
          flexShrink: 0,
        }}>
          {avatar}
        </div>
      )}
      
      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          <span style={{ 
            fontWeight: 600, 
            fontSize: '14px',
            color: tokens.textPrimary,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {title}
          </span>
          {badge && (
            <span style={{
              background: badgeColors[badgeColor].bg,
              color: badgeColors[badgeColor].text,
              padding: '2px 8px',
              borderRadius: '6px',
              fontSize: '10px',
              fontWeight: 600,
              flexShrink: 0,
            }}>
              {badge}
            </span>
          )}
        </div>
        {subtitle && (
          <div style={{ 
            fontSize: '13px', 
            color: tokens.textMuted,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {subtitle}
          </div>
        )}
      </div>
      
      {/* Meta / Right Content */}
      {(meta || rightContent) && (
        <div style={{ 
          textAlign: 'right',
          flexShrink: 0,
        }}>
          {meta && (
            <div style={{ 
              fontSize: '12px', 
              color: metaColor || tokens.textMuted,
              fontWeight: 500,
            }}>
              {meta}
            </div>
          )}
          {rightContent}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Empty State Component
// ============================================================
function EmptyState({ icon, message }: { icon: string; message: string }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '48px 24px',
      textAlign: 'center',
    }}>
      <div style={{
        width: '56px',
        height: '56px',
        borderRadius: tokens.radiusLg,
        background: tokens.glassBg,
        border: `1px solid ${tokens.glassBorder}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '24px',
        marginBottom: '16px',
      }}>
        {icon}
      </div>
      <div style={{ 
        fontSize: '14px', 
        color: tokens.textMuted,
        fontWeight: 500,
      }}>
        {message}
      </div>
    </div>
  );
}

// ============================================================
// Loading Skeleton
// ============================================================
function SkeletonItem() {
  return (
    <div style={{
      padding: '14px 20px',
      borderBottom: `1px solid ${tokens.glassBorder}`,
      display: 'flex',
      alignItems: 'center',
      gap: '14px',
    }}>
      <div style={{
        width: '40px',
        height: '40px',
        borderRadius: tokens.radiusMd,
        background: `linear-gradient(90deg, ${tokens.glassBg} 25%, ${tokens.bgSurfaceHover} 50%, ${tokens.glassBg} 75%)`,
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s infinite',
      }} />
      <div style={{ flex: 1 }}>
        <div style={{
          width: '60%',
          height: '14px',
          borderRadius: '4px',
          background: tokens.glassBg,
          marginBottom: '8px',
        }} />
        <div style={{
          width: '40%',
          height: '12px',
          borderRadius: '4px',
          background: tokens.glassBg,
        }} />
      </div>
    </div>
  );
}

// ============================================================
// Main Dashboard Component
// ============================================================
export function DashboardPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummaryDTO | null>(null);
  const [pendingReservations, setPendingReservations] = useState<PendingReservationDTO[]>([]);
  const [unansweredMessages, setUnansweredMessages] = useState<UnansweredMessageDTO[]>([]);
  const [staffAlerts, setStaffAlerts] = useState<StaffAlertDTO[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, reservationsRes, messagesRes, alertsRes] = await Promise.all([
        getDashboardSummary(),
        getPendingReservations(),
        getUnansweredMessages(),
        getStaffAlerts(),
      ]);
      setSummary(summaryRes);
      setPendingReservations((reservationsRes.items || []).slice(0, 5));
      setUnansweredMessages((messagesRes.items || []).slice(0, 6));
      setStaffAlerts((alertsRes.items || []).slice(0, 5));
    } catch (err) {
      setError("데이터를 불러오는 중 오류가 발생했습니다.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Helper functions
  const formatTime = (hours: number) => {
    if (hours < 1) return "방금 전";
    if (hours < 24) return `${Math.round(hours)}시간 전`;
    return `${Math.round(hours / 24)}일 전`;
  };
  
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <PageLayout>
      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
      
      <div style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        height: '100%',
        background: tokens.bgBase,
      }}>
        {/* Page Header */}
        <header style={{
          padding: '24px 32px',
          borderBottom: `1px solid ${tokens.glassBorder}`,
          background: tokens.bgElevated,
        }}>
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between' 
          }}>
            <div>
              <h1 style={{ 
                fontSize: '24px', 
                fontWeight: 700, 
                color: tokens.textPrimary,
                margin: 0,
                letterSpacing: '-0.02em',
              }}>
                대시보드
              </h1>
              <p style={{ 
                fontSize: '14px', 
                color: tokens.textMuted,
                margin: '4px 0 0 0',
              }}>
                운영 현황을 한눈에 확인하세요
              </p>
            </div>
            <button
              onClick={fetchData}
              disabled={loading}
              style={{
                background: tokens.glassBg,
                border: `1px solid ${tokens.glassBorder}`,
                borderRadius: tokens.radiusMd,
                padding: '10px 18px',
                color: tokens.textPrimary,
                fontSize: '13px',
                fontWeight: 500,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.5 : 1,
                transition: 'all 0.15s',
              }}
            >
              {loading ? '로딩...' : '새로고침'}
            </button>
          </div>
        </header>

        {/* Error Alert */}
        {error && (
          <div style={{
            margin: '24px 32px 0',
            padding: '14px 18px',
            background: tokens.dangerMuted,
            border: `1px solid rgba(239, 68, 68, 0.3)`,
            borderRadius: tokens.radiusMd,
            color: tokens.danger,
            fontSize: '14px',
          }}>
            {error}
          </div>
        )}

        {/* Summary Cards */}
        {summary && (
          <div style={{
            display: 'flex',
            gap: '16px',
            padding: '24px 32px',
            overflowX: 'auto',
          }}>
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

        {/* Main Content Grid */}
        <div style={{ 
          flex: 1, 
          padding: '0 32px 32px', 
          display: 'flex', 
          flexDirection: 'column', 
          gap: '20px',
          minHeight: 0,
          overflow: 'hidden',
        }}>
          
          {/* Top Row: 미응답 메시지 (Full Width) */}
          <Card
            title="미응답 메시지"
            icon="💬"
            badge={summary?.unanswered_messages_count}
            badgeColor="danger"
            onViewAll={() => navigate("/inbox?is_read=false")}
            style={{ flex: 1, minHeight: '220px' }}
          >
            {loading ? (
              <>
                <SkeletonItem />
                <SkeletonItem />
                <SkeletonItem />
              </>
            ) : unansweredMessages.length === 0 ? (
              <EmptyState icon="✓" message="미응답 메시지가 없습니다" />
            ) : (
              unansweredMessages.map((item) => (
                <ListItem
                  key={item.conversation_id}
                  avatar={item.guest_name?.charAt(0) || "?"}
                  title={item.guest_name || "게스트"}
                  subtitle={item.last_message_preview?.slice(0, 50) || "메시지 없음"}
                  badge={item.property_code || undefined}
                  badgeColor="primary"
                  meta={formatTime(item.hours_since_last_message ?? 0)}
                  metaColor={
                    (item.hours_since_last_message ?? 0) > 12 
                      ? tokens.danger 
                      : (item.hours_since_last_message ?? 0) > 6 
                        ? tokens.warning 
                        : tokens.textMuted
                  }
                  onClick={() => navigate(`/inbox?conversation_id=${item.conversation_id}`)}
                />
              ))
            )}
          </Card>

          {/* Bottom Row: 2 Column Grid */}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '1fr 1fr', 
            gap: '20px', 
            flex: 1,
            minHeight: '220px',
          }}>
            {/* 예약 요청 */}
            <Card
              title="예약 요청"
              icon="📩"
              badge={pendingReservations.length}
              badgeColor="warning"
              onViewAll={() => navigate("/booking-requests")}
            >
              {loading ? (
                <>
                  <SkeletonItem />
                  <SkeletonItem />
                </>
              ) : pendingReservations.length === 0 ? (
                <EmptyState icon="✓" message="대기 중인 예약 요청이 없습니다" />
              ) : (
                pendingReservations.map((item) => {
                  const remaining = item.remaining_hours ?? 0;
                  const isUrgent = remaining <= 6;
                  const isExpiring = remaining <= 12 && remaining > 6;
                  
                  return (
                    <ListItem
                      key={item.id}
                      statusBar={isUrgent ? 'danger' : isExpiring ? 'warning' : 'primary'}
                      title={item.guest_name || "게스트"}
                      subtitle={`${formatDate(item.checkin_date)} ~ ${formatDate(item.checkout_date)} · ${item.nights || 0}박`}
                      badge={item.property_code || undefined}
                      badgeColor="primary"
                      meta={remaining > 0 ? `${Math.round(remaining)}시간 남음` : "만료됨"}
                      metaColor={isUrgent ? tokens.danger : isExpiring ? tokens.warning : tokens.textMuted}
                      onClick={() => navigate(`/booking-requests?id=${item.id}`)}
                    />
                  );
                })
              )}
            </Card>

            {/* Staff Alerts */}
            <Card
              title="Staff Alerts"
              icon="🔔"
              badge={staffAlerts.length}
              badgeColor="danger"
              onViewAll={() => navigate("/staff-notifications")}
            >
              {loading ? (
                <>
                  <SkeletonItem />
                  <SkeletonItem />
                </>
              ) : staffAlerts.length === 0 ? (
                <EmptyState icon="✓" message="Staff Alerts가 없습니다" />
              ) : (
                staffAlerts.map((item) => (
                  <ListItem
                    key={item.oc_id}
                    statusBar="danger"
                    title={item.guest_name || "알림"}
                    subtitle={item.alert_reason || "Staff 확인 필요"}
                    badge={item.property_code || undefined}
                    badgeColor="danger"
                    meta={item.created_at ? new Date(item.created_at).toLocaleDateString() : ""}
                    onClick={() => navigate(`/staff-notifications?oc_id=${item.oc_id}`)}
                  />
                ))
              )}
            </Card>
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
