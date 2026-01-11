// src/api/calendar.ts

import { apiGet, apiPost, apiPut } from "./client";
import type { 
  CalendarMonthDTO, 
  OccupancyDTO, 
  IcalSyncResultDTO,
  AvailabilityCheckRequest,
  AvailabilityCheckResponse,
  PropertyListItem,
} from "../types/calendar";

/**
 * 월간 달력 데이터 조회
 */
export function getCalendar(
  propertyCode: string,
  params?: { year?: number; month?: number }
): Promise<CalendarMonthDTO> {
  return apiGet<CalendarMonthDTO>(`/calendar/${propertyCode}`, params);
}

/**
 * 점유율 조회
 */
export function getOccupancy(
  propertyCode: string,
  params?: { start?: string; end?: string }
): Promise<OccupancyDTO> {
  return apiGet<OccupancyDTO>(`/calendar/${propertyCode}/occupancy`, params);
}

/**
 * iCal 동기화
 */
export function syncIcal(propertyCode: string): Promise<IcalSyncResultDTO> {
  return apiPost<IcalSyncResultDTO>(`/calendar/${propertyCode}/sync`);
}

/**
 * iCal URL 설정
 */
export function updateIcalUrl(
  propertyCode: string,
  icalUrl: string
): Promise<{ message: string; property_code: string }> {
  return apiPut(`/calendar/${propertyCode}/ical-url`, { ical_url: icalUrl });
}

/**
 * 예약 가능 여부 체크
 */
export function checkAvailability(
  request: AvailabilityCheckRequest
): Promise<AvailabilityCheckResponse> {
  return apiPost<AvailabilityCheckResponse>(`/calendar/check-availability`, request);
}

/**
 * 숙소 목록 (달력용)
 */
export function getPropertiesForCalendar(): Promise<PropertyListItem[]> {
  return apiGet<PropertyListItem[]>(`/calendar/properties/list`);
}
