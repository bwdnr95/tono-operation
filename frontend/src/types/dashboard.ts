// src/types/dashboard.ts
// Dashboard 관련 타입 정의

// ============================================================
// Dashboard Summary
// ============================================================

export interface DashboardSummaryDTO {
  pending_reservations_count: number;
  unanswered_messages_count: number;
  staff_alerts_count: number;
  today_checkins_count: number;
  today_checkouts_count: number;
}

// ============================================================
// Pending Reservation Request
// ============================================================

export type PendingReservationStatus = 
  | "pending" 
  | "accepted" 
  | "declined" 
  | "expired";

export interface PendingReservationDTO {
  id: number;
  reservation_code: string | null;
  property_code: string | null;
  listing_name: string | null;
  guest_name: string | null;
  guest_message: string | null;
  guest_verified: boolean;
  guest_review_count: number | null;
  checkin_date: string | null;  // ISO format
  checkout_date: string | null; // ISO format
  nights: number | null;
  guest_count: number | null;
  expected_payout: number | null;
  action_url: string | null;
  status: PendingReservationStatus;
  remaining_hours: number | null;
  received_at: string | null;  // ISO format
  airbnb_thread_id: string | null;  // for navigation from notifications
}

export interface PendingReservationListResponse {
  items: PendingReservationDTO[];
  total_count: number;
}

// ============================================================
// Unanswered Message
// ============================================================

export interface UnansweredMessageDTO {
  conversation_id: string;  // UUID
  airbnb_thread_id: string;
  property_code: string | null;
  property_name: string | null;
  guest_name: string | null;
  last_message_preview: string | null;
  last_message_at: string | null;  // ISO format
  hours_since_last_message: number | null;
}

export interface UnansweredMessageListResponse {
  items: UnansweredMessageDTO[];
  total_count: number;
}

// ============================================================
// Staff Alert
// ============================================================

export interface StaffAlertDTO {
  oc_id: string;  // UUID
  conversation_id: string;  // UUID
  airbnb_thread_id: string;
  property_code: string | null;
  property_name: string | null;
  guest_name: string | null;
  topic: string;
  description: string;
  target_date: string | null;  // ISO format
  status: string;
  priority: string;
  created_at: string | null;  // ISO format
}

export interface StaffAlertListResponse {
  items: StaffAlertDTO[];
  total_count: number;
}
