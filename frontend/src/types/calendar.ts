// src/types/calendar.ts

export type CalendarDayType = 
  | "available" 
  | "reserved" 
  | "blocked" 
  | "checkin" 
  | "checkout";

export interface CalendarDayDTO {
  date: string;  // "YYYY-MM-DD"
  type: CalendarDayType;
  guest_name: string | null;
  reservation_code: string | null;
  summary: string | null;  // iCal 차단 사유
}

export interface CalendarMonthDTO {
  property_code: string;
  property_name: string;
  year: number;
  month: number;
  days: CalendarDayDTO[];
  occupancy_rate: number;  // 0~100
  reserved_days: number;
  blocked_days: number;
  available_days: number;
  total_days: number;
}

export interface OccupancyDTO {
  property_code: string;
  property_name: string;
  period_start: string;
  period_end: string;
  occupancy_rate: number;
  reserved_days: number;
  blocked_days: number;
  available_days: number;
  total_days: number;
}

export interface IcalSyncResultDTO {
  property_code: string;
  synced_dates: number;
  last_synced_at: string;
}

export interface ConflictDTO {
  date: string;
  type: "reservation" | "blocked";
  guest_name: string | null;
  summary: string | null;
}

export interface AvailabilityCheckRequest {
  property_code: string;
  checkin_date: string;
  checkout_date: string;
}

export interface AvailabilityCheckResponse {
  available: boolean;
  conflicts: ConflictDTO[];
  message: string;
}

export interface PropertyListItem {
  property_code: string;
  name: string;
  has_ical: boolean;
  last_synced_at: string | null;
}
