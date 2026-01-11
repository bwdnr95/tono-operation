// src/types/reservations.ts
/**
 * Reservation 관련 타입 정의
 */

export type ReservationStatus =
  | "inquiry"
  | "awaiting_approval"
  | "declined"
  | "expired"
  | "confirmed"
  | "canceled"
  | "alteration_requested"
  | "pending";

export interface Reservation {
  id: number;
  airbnb_thread_id: string;
  status: ReservationStatus;

  guest_name?: string;
  guest_count?: number;
  child_count?: number;
  infant_count?: number;
  pet_count?: number;

  reservation_code?: string;
  checkin_date?: string;
  checkout_date?: string;

  property_code?: string;
  group_code?: string;
  listing_id?: string;
  listing_name?: string;

  // 추가 정보 (JOIN)
  property_name?: string;
  group_name?: string;
  room_assigned: boolean;
  
  // 🆕 실제 적용되는 그룹 코드 (property의 group_code 포함)
  effective_group_code?: string;
  can_reassign: boolean;  // 객실 재배정 가능 여부

  created_at: string;
  updated_at: string;
}

export interface AvailableRoom {
  property_code: string;
  name: string;
  bed_types?: string;
  capacity_max?: number;
  is_available: boolean;
  conflict_info?: string; // 충돌 예약 정보
}

export interface RoomAssignmentInfo {
  reservation: Reservation;
  group?: {
    group_code: string;
    name: string;
  };
  available_rooms: AvailableRoom[];
}

export interface RoomAssignRequest {
  property_code: string;
}

export interface ReservationListParams {
  status?: ReservationStatus;
  group_code?: string;
  property_code?: string;
  unassigned_only?: boolean;
  checkin_from?: string;
  checkin_to?: string;
  checkout_from?: string;
  checkout_to?: string;
  search?: string;  // 게스트명 또는 예약코드 검색
  limit?: number;
  offset?: number;
}

export interface ReservationListResponse {
  items: Reservation[];
  total: number;
  limit: number;
  offset: number;
}
