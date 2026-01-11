// src/api/reservations.ts
/**
 * Reservation API - 예약 조회 및 객실 배정
 */
import { apiGet, apiPatch, apiDelete } from "./client";
import type {
  Reservation,
  RoomAssignmentInfo,
  RoomAssignRequest,
  ReservationListParams,
  ReservationListResponse,
} from "../types/reservations";

/**
 * 예약 목록 조회
 */
export function getReservations(
  params?: ReservationListParams
): Promise<Reservation[]> {
  return apiGet<Reservation[]>("/reservations", params as Record<string, unknown>);
}

/**
 * 예약 목록 조회 (페이지네이션 포함)
 */
export function getReservationsPaginated(
  params?: ReservationListParams
): Promise<ReservationListResponse> {
  return apiGet<ReservationListResponse>("/reservations/paginated", params as Record<string, unknown>);
}

/**
 * 예약 상세 조회
 */
export function getReservation(threadId: string): Promise<Reservation> {
  return apiGet<Reservation>(`/reservations/${threadId}`);
}

/**
 * 객실 배정 정보 조회 (가능한 객실 목록 포함)
 */
export function getRoomAssignmentInfo(threadId: string): Promise<RoomAssignmentInfo> {
  return apiGet<RoomAssignmentInfo>(`/reservations/${threadId}/room-assignment`);
}

/**
 * 객실 배정/변경
 */
export function assignRoom(
  threadId: string,
  data: RoomAssignRequest
): Promise<Reservation> {
  return apiPatch<Reservation, RoomAssignRequest>(
    `/reservations/${threadId}/assign-room`,
    data
  );
}

/**
 * 객실 배정 해제
 */
export function unassignRoom(threadId: string): Promise<Reservation> {
  return apiDelete<Reservation>(`/reservations/${threadId}/assign-room`);
}
