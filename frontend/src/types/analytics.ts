// src/types/analytics.ts

export interface AnalyticsSummaryDTO {
  period: string;
  start_date: string;
  end_date: string;
  
  // 운영 지표
  reservations_confirmed: number;
  messages_sent: number;
  avg_response_minutes: number | null;
  ai_adoption_rate: number | null;
  
  // 수익 지표
  lead_time_days: number | null;
  adr: number | null;
  occupancy_rate: number | null;
  
  // 변화율
  reservations_confirmed_change: number | null;
  messages_sent_change: number | null;
  avg_response_change: number | null;
  ai_adoption_change: number | null;
}

export interface TrendItemDTO {
  month: string;
  reservations_confirmed: number;
  messages_sent: number;
  avg_response_minutes: number | null;
  ai_adoption_rate: number | null;
  lead_time_days: number | null;
  adr: number | null;
  occupancy_rate: number | null;
}

export interface TrendResponse {
  items: TrendItemDTO[];
}

export interface PropertyComparisonDTO {
  property_code: string;
  property_name: string | null;
  reservations_confirmed: number;
  messages_sent: number;
  avg_response_minutes: number | null;
  ai_adoption_rate: number | null;
  lead_time_days: number | null;
  adr: number | null;
  occupancy_rate: number | null;
}

export interface PropertyComparisonResponse {
  items: PropertyComparisonDTO[];
}

export type PeriodType = "today" | "week" | "month" | "custom";

// =============================================================================
// OC Analytics Types
// =============================================================================

export interface OCTopicCountDTO {
  topic: string;
  topic_label: string;
  count: number;
  percentage: number;
}

export interface OCStatusCountDTO {
  status: string;
  status_label: string;
  count: number;
}

export interface OCSummaryDTO {
  period: string;
  start_date: string;
  end_date: string;
  
  total_count: number;
  completed_count: number;
  completion_rate: number | null;
  
  total_count_change: number | null;
  
  by_topic: OCTopicCountDTO[];
  by_status: OCStatusCountDTO[];
}

export interface OCTrendItemDTO {
  month: string;
  total_count: number;
  completed_count: number;
  by_topic: OCTopicCountDTO[];
}

export interface OCTrendResponse {
  items: OCTrendItemDTO[];
}

export interface OCByPropertyDTO {
  property_code: string;
  property_name: string | null;
  total_count: number;
  by_topic: OCTopicCountDTO[];
}

export interface OCByPropertyResponse {
  items: OCByPropertyDTO[];
}

// =============================================================================
// OC 히트맵
// =============================================================================

export interface OCHeatmapCellDTO {
  topic: string;
  topic_label: string;
  count: number;
}

export interface OCHeatmapRowDTO {
  property_code: string;
  property_name: string | null;
  total_count: number;
  cells: OCHeatmapCellDTO[];
}

export interface OCHeatmapResponse {
  topics: string[];
  topic_labels: Record<string, string>;
  rows: OCHeatmapRowDTO[];
}

// =============================================================================
// OC 상세 목록
// =============================================================================

export interface OCDetailItemDTO {
  oc_id: string;
  conversation_id: string;
  description: string;
  evidence_quote: string | null;
  status: string;
  status_label: string;
  target_date: string | null;
  created_at: string;
  guest_name: string | null;
  checkin_date: string | null;
  checkout_date: string | null;
}

export interface OCDetailListResponse {
  property_code: string;
  property_name: string | null;
  topic: string;
  topic_label: string;
  total_count: number;
  items: OCDetailItemDTO[];
}
