// src/api/dashboard.ts
/**
 * Dashboard API
 * - 대시보드 요약, 예약 요청, 미응답 메시지, Staff Alerts
 */
import { apiGet } from "./client";

import type {
  DashboardSummaryDTO,
  PendingReservationListResponse,
  UnansweredMessageListResponse,
  StaffAlertListResponse,
} from "../types/dashboard";

// ============================================================
// Dashboard Summary
// ============================================================

// GET /api/v1/dashboard/summary
export async function getDashboardSummary(
  propertyCode?: string | null
): Promise<DashboardSummaryDTO> {
  return apiGet<DashboardSummaryDTO>("/dashboard/summary", {
    property_code: propertyCode,
  });
}

// ============================================================
// Pending Reservations (예약 요청)
// ============================================================

export interface GetPendingReservationsParams {
  property_code?: string | null;
  include_expired?: boolean;
  limit?: number;
}

// GET /api/v1/dashboard/pending-requests
export async function getPendingReservations(
  params?: GetPendingReservationsParams
): Promise<PendingReservationListResponse> {
  return apiGet<PendingReservationListResponse>("/dashboard/pending-requests", params);
}

// ============================================================
// Unanswered Messages (미응답 메시지)
// ============================================================

export interface GetUnansweredMessagesParams {
  property_code?: string | null;
  hours_threshold?: number;
  limit?: number;
}

// GET /api/v1/dashboard/unanswered-messages
export async function getUnansweredMessages(
  params?: GetUnansweredMessagesParams
): Promise<UnansweredMessageListResponse> {
  return apiGet<UnansweredMessageListResponse>("/dashboard/unanswered-messages", params);
}

// ============================================================
// Staff Alerts
// ============================================================

export interface GetStaffAlertsParams {
  property_code?: string | null;
  limit?: number;
}

// GET /api/v1/dashboard/staff-alerts
export async function getStaffAlerts(
  params?: GetStaffAlertsParams
): Promise<StaffAlertListResponse> {
  return apiGet<StaffAlertListResponse>("/dashboard/staff-alerts", params);
}

// ============================================================
// Aliases for backward compatibility
// ============================================================
export const getDashboardStaffAlerts = getStaffAlerts;
export const getDashboardPendingReservations = getPendingReservations;
export const getDashboardUnansweredMessages = getUnansweredMessages;
