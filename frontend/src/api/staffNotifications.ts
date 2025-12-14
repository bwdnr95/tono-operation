// src/api/staffNotifications.ts
import { apiGet, apiPatch } from "./client";
import type { StaffNotificationDTO } from "../types/intents";

export interface StaffNotificationFilters extends Record<string, unknown> {
  unresolved_only?: boolean;
  limit?: number;
}

// GET /api/v1/staff-notifications
export async function fetchStaffNotifications(
  filters: StaffNotificationFilters = {},
): Promise<StaffNotificationDTO[]> {
  return apiGet<StaffNotificationDTO[]>("/staff-notifications", filters);
}

// PATCH /api/v1/staff-notifications/{id}
export async function updateStaffNotificationStatus(
  id: number,
  status: StaffNotificationDTO["status"],
): Promise<StaffNotificationDTO> {
  // ✅ 여기서 body = { status: "RESOLVED" } 형태로 정확히 전달
  return apiPatch<StaffNotificationDTO, { status: StaffNotificationDTO["status"] }>(
    `/staff-notifications/${id}`,
    { status },
  );
}
