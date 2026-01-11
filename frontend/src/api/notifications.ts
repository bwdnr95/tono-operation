// src/api/notifications.ts
/**
 * In-App Notification API
 */
import { apiGet, apiPost, apiDelete } from "./client";

// ============================================================
// Types
// ============================================================

export interface NotificationDTO {
  id: string;
  type: string;
  priority: "critical" | "high" | "normal" | "low";
  title: string;
  body: string | null;
  link_type: string | null;
  link_id: string | null;
  property_code: string | null;
  guest_name: string | null;
  airbnb_thread_id: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: NotificationDTO[];
  total: number;
  unread_count: number;
}

export interface NotificationCountResponse {
  count: number;
}

export interface NotificationSummaryResponse {
  total: number;
  critical: number;
  high: number;
  normal: number;
  low: number;
}

export interface MarkReadResponse {
  success: boolean;
  notification_id: string | null;
}

export interface MarkAllReadResponse {
  success: boolean;
  count: number;
}

export interface DeleteResponse {
  success: boolean;
  deleted_count?: number;
}

// ============================================================
// API Functions
// ============================================================

export const notificationApi = {
  /**
   * 알림 목록 조회
   */
  getNotifications: (params?: {
    unread_only?: boolean;
    type_filter?: string;
    limit?: number;
  }): Promise<NotificationListResponse> => {
    return apiGet<NotificationListResponse>("/notifications", params);
  },

  /**
   * 미읽음 알림 개수
   */
  getUnreadCount: (): Promise<NotificationCountResponse> => {
    return apiGet<NotificationCountResponse>("/notifications/count");
  },

  /**
   * 우선순위별 미읽음 요약
   */
  getSummary: (): Promise<NotificationSummaryResponse> => {
    return apiGet<NotificationSummaryResponse>("/notifications/summary");
  },

  /**
   * 특정 알림 읽음 처리
   */
  markAsRead: (notificationId: string): Promise<MarkReadResponse> => {
    return apiPost<MarkReadResponse>(`/notifications/${notificationId}/read`);
  },

  /**
   * 모든 알림 읽음 처리
   */
  markAllAsRead: (): Promise<MarkAllReadResponse> => {
    return apiPost<MarkAllReadResponse>("/notifications/read-all");
  },

  /**
   * 특정 알림 삭제
   */
  deleteNotification: (notificationId: string): Promise<DeleteResponse> => {
    return apiDelete<DeleteResponse>(`/notifications/${notificationId}`);
  },

  /**
   * 모든 알림 삭제
   */
  deleteAllNotifications: (): Promise<DeleteResponse> => {
    return apiDelete<DeleteResponse>("/notifications");
  },
};
