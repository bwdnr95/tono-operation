// src/components/notifications/NotificationBell.tsx
/**
 * In-App 알림 Bell 아이콘 + 드롭다운
 * - 사이드바 헤더에 표시
 * - 미읽음 개수 뱃지
 * - 클릭 시 드롭다운 표시
 * - 개별/전체 삭제 기능
 * - Browser Push 알림 설정
 */
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { notificationApi, type NotificationDTO } from "../../api/notifications";
import {
  isPushSupported,
  getCurrentSubscription,
  createPushSubscription,
  cancelPushSubscription,
} from "../../api/push";
import { useToast } from "../ui/Toast";

// ============================================================
// Priority 색상 맵핑
// ============================================================

const priorityConfig = {
  critical: {
    bg: "var(--danger-bg)",
    border: "var(--danger)",
    icon: "🔴",
    color: "var(--danger)",
  },
  high: {
    bg: "var(--warning-bg)",
    border: "var(--warning)",
    icon: "🟠",
    color: "var(--warning)",
  },
  normal: {
    bg: "var(--primary-bg)",
    border: "var(--primary)",
    icon: "🔵",
    color: "var(--primary)",
  },
  low: {
    bg: "var(--bg-secondary)",
    border: "var(--border)",
    icon: "⚪",
    color: "var(--text-secondary)",
  },
};

// ============================================================
// 시간 포맷 헬퍼
// ============================================================

function formatTimeAgo(dateString: string): string {
  const now = new Date();
  // 서버가 UTC 시간을 보내지만 'Z'가 없으면 로컬로 해석되므로 UTC로 강제 변환
  const utcDateString = dateString.endsWith('Z') ? dateString : dateString + 'Z';
  const date = new Date(utcDateString);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "방금 전";
  if (diffMins < 60) return `${diffMins}분 전`;
  if (diffHours < 24) {
    const remainingMins = diffMins % 60;
    if (remainingMins === 0) return `${diffHours}시간 전`;
    return `${diffHours}시간 ${remainingMins}분 전`;
  }
  if (diffDays < 7) return `${diffDays}일 전`;
  return date.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

// ============================================================
// NotificationItem
// ============================================================

interface NotificationItemProps {
  notification: NotificationDTO;
  onRead: (id: string) => void;
  onDelete: (id: string) => void;
  onNavigate: (notification: NotificationDTO) => void;
}

function NotificationItem({ notification, onRead, onDelete, onNavigate }: NotificationItemProps) {
  const config = priorityConfig[notification.priority as keyof typeof priorityConfig] || priorityConfig.normal;
  const [showDelete, setShowDelete] = useState(false);

  const handleClick = () => {
    if (!notification.is_read) {
      onRead(notification.id);
    }
    onNavigate(notification);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete(notification.id);
  };

  return (
    <div
      onClick={handleClick}
      onMouseEnter={() => setShowDelete(true)}
      onMouseLeave={() => setShowDelete(false)}
      style={{
        padding: "12px 16px",
        borderBottom: "1px solid var(--border)",
        cursor: "pointer",
        backgroundColor: notification.is_read ? "var(--surface)" : config.bg,
        borderLeft: notification.is_read ? "none" : `3px solid ${config.color}`,
        transition: "background-color 0.15s ease",
        position: "relative",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
        <span style={{ fontSize: "14px" }}>{config.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: "13px",
              fontWeight: notification.is_read ? 400 : 600,
              color: "var(--text)",
              marginBottom: "4px",
              paddingRight: "24px", // 삭제 버튼 공간
            }}
          >
            {notification.title}
          </div>
          {notification.body && (
            <div
              style={{
                fontSize: "12px",
                color: "#6b7280",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {notification.body}
            </div>
          )}
          <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "4px" }}>
            {formatTimeAgo(notification.created_at)}
          </div>
        </div>
      </div>
      
      {/* 삭제 버튼 */}
      {showDelete && (
        <button
          onClick={handleDelete}
          style={{
            position: "absolute",
            top: "12px",
            right: "12px",
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: "4px",
            borderRadius: "4px",
            color: "var(--text-muted)",
            fontSize: "14px",
            lineHeight: 1,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = "var(--danger-bg)";
            e.currentTarget.style.color = "var(--danger)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = "transparent";
            e.currentTarget.style.color = "var(--text-muted)";
          }}
          title="삭제"
        >
          ✕
        </button>
      )}
    </div>
  );
}

// ============================================================
// NotificationBell
// ============================================================

export function NotificationBell() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationDTO[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const prevUnreadCount = useRef(0);

  // Push 알림 상태
  const [pushSupported, setPushSupported] = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushLoading, setPushLoading] = useState(false);

  // Push 상태 확인
  useEffect(() => {
    const checkPushStatus = async () => {
      const supported = isPushSupported();
      setPushSupported(supported);
      if (supported) {
        const subscription = await getCurrentSubscription();
        setPushEnabled(!!subscription);
      }
    };
    checkPushStatus();
  }, []);

  // Push 토글 핸들러
  const handlePushToggle = async () => {
    setPushLoading(true);
    try {
      if (pushEnabled) {
        await cancelPushSubscription();
        setPushEnabled(false);
        showToast({ type: "success", title: "브라우저 Push 알림 꺼짐" });
      } else {
        const subscription = await createPushSubscription();
        if (subscription) {
          setPushEnabled(true);
          showToast({ type: "success", title: "브라우저 Push 알림 켜짐", message: "브라우저를 닫아도 알림을 받습니다." });
        } else {
          showToast({ type: "error", title: "알림 권한 필요", message: "브라우저에서 알림을 허용해주세요." });
        }
      }
    } catch (error) {
      console.error("Push toggle error:", error);
      showToast({ type: "error", title: "오류 발생" });
    } finally {
      setPushLoading(false);
    }
  };

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 알림 목록 fetch
  const fetchNotifications = useCallback(async () => {
    try {
      const data = await notificationApi.getNotifications({ limit: 20 });
      setNotifications(data.notifications);
      setUnreadCount(data.unread_count);

      // 새 알림이 있으면 Toast 표시
      if (data.unread_count > prevUnreadCount.current && prevUnreadCount.current > 0) {
        const newNotifications = data.notifications.filter((n) => !n.is_read);
        if (newNotifications.length > 0) {
          const latest = newNotifications[0];
          showToast({
            type: latest.priority === "critical" ? "error" : latest.priority === "high" ? "warning" : "info",
            title: latest.title,
            message: latest.body || undefined,
          });
        }
      }
      prevUnreadCount.current = data.unread_count;
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    }
  }, [showToast]);

  // 초기 로드 + 30초마다 폴링
  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // 읽음 처리
  const handleRead = async (id: string) => {
    try {
      await notificationApi.markAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch (err) {
      console.error("Failed to mark notification as read:", err);
    }
  };

  // 전체 읽음 처리
  const handleReadAll = async () => {
    try {
      await notificationApi.markAllAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (err) {
      console.error("Failed to mark all as read:", err);
    }
  };

  // 개별 삭제
  const handleDelete = async (id: string) => {
    try {
      await notificationApi.deleteNotification(id);
      const deleted = notifications.find((n) => n.id === id);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
      if (deleted && !deleted.is_read) {
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
      showToast({
        type: "success",
        title: "알림 삭제됨",
      });
    } catch (err) {
      console.error("Failed to delete notification:", err);
      showToast({
        type: "error",
        title: "삭제 실패",
      });
    }
  };

  // 전체 삭제
  const handleDeleteAll = async () => {
    try {
      const result = await notificationApi.deleteAllNotifications();
      setNotifications([]);
      setUnreadCount(0);
      showToast({
        type: "success",
        title: "알림 삭제 완료",
        message: `${result.deleted_count || 0}개의 알림이 삭제되었습니다.`,
      });
    } catch (err) {
      console.error("Failed to delete all notifications:", err);
      showToast({
        type: "error",
        title: "삭제 실패",
        message: "알림 삭제 중 오류가 발생했습니다.",
      });
    }
  };

  // 알림 클릭 시 네비게이션
  const handleNavigate = (notification: NotificationDTO) => {
    setIsOpen(false);
    
    // 메시지 관련 (conversation, new_guest_message, safety_alert 등)
    if (notification.link_type === "conversation" && notification.airbnb_thread_id) {
      navigate(`/inbox?thread=${notification.airbnb_thread_id}`);
    } 
    // Staff Notification (OC 리마인더 등)
    else if (notification.link_type === "staff_notification") {
      navigate("/staff-notifications");
    } 
    // 예약 관련 (booking_confirmed, booking_cancelled, booking_rtb, same_day_checkin)
    else if (notification.link_type === "reservation") {
      // RTB는 booking-requests 페이지로, 나머지는 thread가 있으면 inbox로
      if (notification.type === "booking_rtb" && notification.airbnb_thread_id) {
        navigate(`/booking-requests?thread=${notification.airbnb_thread_id}`);
      } else if (notification.airbnb_thread_id) {
        navigate(`/inbox?thread=${notification.airbnb_thread_id}`);
      } else {
        navigate("/booking-requests");
      }
    }
  };

  return (
    <div ref={dropdownRef} style={{ position: "relative" }}>
      {/* Bell 버튼 - 사이드바용 (밝은 색상) */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          position: "relative",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: "8px",
          borderRadius: "8px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = "rgba(255, 255, 255, 0.1)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = "transparent";
        }}
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ color: "rgba(255, 255, 255, 0.8)" }}
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>

        {/* 미읽음 뱃지 */}
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: "2px",
              right: "2px",
              minWidth: "16px",
              height: "16px",
              padding: "0 4px",
              borderRadius: "8px",
              backgroundColor: "var(--danger)",
              color: "white",
              fontSize: "10px",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* 드롭다운 - 데스크톱: 왼쪽, 모바일: 오른쪽 */}
      {isOpen && (
        <div
          className="notification-dropdown"
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            left: 0,
            width: "360px",
            maxHeight: "480px",
            backgroundColor: "var(--surface)",
            borderRadius: "12px",
            boxShadow: "var(--shadow-lg)",
            border: "1px solid var(--border)",
            overflow: "hidden",
            zIndex: 1000,
          }}
        >
          {/* 헤더 */}
          <div
            style={{
              padding: "14px 16px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              backgroundColor: "var(--surface)",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: "14px", color: "var(--text)" }}>
              알림 {unreadCount > 0 && `(${unreadCount})`}
            </span>
            <div style={{ display: "flex", gap: "8px" }}>
              {unreadCount > 0 && (
                <button
                  onClick={handleReadAll}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--accent)",
                    fontSize: "12px",
                    cursor: "pointer",
                    padding: "4px 8px",
                    borderRadius: "4px",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = "var(--bg-secondary)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  모두 읽음
                </button>
              )}
              {notifications.length > 0 && (
                <button
                  onClick={handleDeleteAll}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    fontSize: "12px",
                    cursor: "pointer",
                    padding: "4px 8px",
                    borderRadius: "4px",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = "var(--danger-bg)";
                    e.currentTarget.style.color = "var(--danger)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "transparent";
                    e.currentTarget.style.color = "var(--text-muted)";
                  }}
                >
                  전체 삭제
                </button>
              )}
            </div>
          </div>

          {/* 알림 목록 */}
          <div style={{ maxHeight: "320px", overflowY: "auto", backgroundColor: "#ffffff" }}>
            {notifications.length === 0 ? (
              <div
                style={{
                  padding: "40px 20px",
                  textAlign: "center",
                  color: "#9ca3af",
                  fontSize: "13px",
                  backgroundColor: "#ffffff",
                }}
              >
                알림이 없습니다
              </div>
            ) : (
              notifications.map((n) => (
                <NotificationItem
                  key={n.id}
                  notification={n}
                  onRead={handleRead}
                  onDelete={handleDelete}
                  onNavigate={handleNavigate}
                />
              ))
            )}
          </div>

          {/* Push 알림 설정 */}
          {pushSupported && (
            <div
              style={{
                padding: "12px 16px",
                borderTop: "1px solid #e5e7eb",
                backgroundColor: "#f9fafb",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ fontSize: "13px", fontWeight: 500, color: "#374151" }}>
                  브라우저 Push 알림
                </div>
                <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>
                  브라우저 닫아도 알림 수신
                </div>
              </div>
              <button
                onClick={handlePushToggle}
                disabled={pushLoading}
                style={{
                  padding: "6px 12px",
                  borderRadius: "6px",
                  border: "none",
                  fontSize: "12px",
                  fontWeight: 500,
                  cursor: pushLoading ? "not-allowed" : "pointer",
                  backgroundColor: pushEnabled ? "#ef4444" : "#3b82f6",
                  color: "white",
                  opacity: pushLoading ? 0.6 : 1,
                  transition: "all 0.15s",
                }}
              >
                {pushLoading ? "..." : pushEnabled ? "끄기" : "켜기"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
