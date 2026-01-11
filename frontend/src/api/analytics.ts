// src/api/analytics.ts
/**
 * Analytics API
 * - 운영 성과 분석 (예약 확정, 메시지 발송, 응답 시간, AI 채택률 등)
 * - OC 분석 (운영 약속 발생 현황)
 */
import { apiGet } from "./client";

import type { 
  AnalyticsSummaryDTO, 
  TrendResponse, 
  PropertyComparisonResponse,
  PeriodType,
  OCSummaryDTO,
  OCTrendResponse,
  OCByPropertyResponse,
  OCHeatmapResponse,
  OCDetailListResponse,
} from "../types/analytics";

// ============================================================
// Analytics Summary
// ============================================================

export interface GetSummaryParams {
  period?: PeriodType;
  start_date?: string;
  end_date?: string;
  property_code?: string;
}

// GET /api/v1/analytics/summary
export async function getAnalyticsSummary(
  params?: GetSummaryParams
): Promise<AnalyticsSummaryDTO> {
  return apiGet<AnalyticsSummaryDTO>("/analytics/summary", params);
}

// ============================================================
// Analytics Trend
// ============================================================

export interface GetTrendParams {
  months?: number;
  property_code?: string;
}

// GET /api/v1/analytics/trend
export async function getAnalyticsTrend(
  params?: GetTrendParams
): Promise<TrendResponse> {
  return apiGet<TrendResponse>("/analytics/trend", params);
}

// ============================================================
// Analytics By Property
// ============================================================

export interface GetByPropertyParams {
  period?: PeriodType;
  start_date?: string;
  end_date?: string;
}

// GET /api/v1/analytics/by-property
export async function getAnalyticsByProperty(
  params?: GetByPropertyParams
): Promise<PropertyComparisonResponse> {
  return apiGet<PropertyComparisonResponse>("/analytics/by-property", params);
}

// ============================================================
// OC Analytics
// ============================================================

// GET /api/v1/analytics/oc/summary
export async function getOCSummary(
  params?: GetSummaryParams
): Promise<OCSummaryDTO> {
  return apiGet<OCSummaryDTO>("/analytics/oc/summary", params);
}

// GET /api/v1/analytics/oc/trend
export async function getOCTrend(
  params?: GetTrendParams
): Promise<OCTrendResponse> {
  return apiGet<OCTrendResponse>("/analytics/oc/trend", params);
}

// GET /api/v1/analytics/oc/by-property
export async function getOCByProperty(
  params?: GetByPropertyParams
): Promise<OCByPropertyResponse> {
  return apiGet<OCByPropertyResponse>("/analytics/oc/by-property", params);
}

// GET /api/v1/analytics/oc/heatmap
export async function getOCHeatmap(): Promise<OCHeatmapResponse> {
  return apiGet<OCHeatmapResponse>("/analytics/oc/heatmap");
}

// GET /api/v1/analytics/oc/detail/{property_code}/{topic}
export async function getOCDetailList(
  propertyCode: string,
  topic: string
): Promise<OCDetailListResponse> {
  return apiGet<OCDetailListResponse>(`/analytics/oc/detail/${propertyCode}/${topic}`);
}

// ============================================================
// Complaint Analytics
// ============================================================

export interface ComplaintHeatmapCellDTO {
  category: string;
  category_label: string;
  count: number;
}

export interface ComplaintHeatmapRowDTO {
  property_code: string;
  property_name: string | null;
  total_count: number;
  cells: ComplaintHeatmapCellDTO[];
}

export interface ComplaintHeatmapResponse {
  categories: string[];
  category_labels: Record<string, string>;
  rows: ComplaintHeatmapRowDTO[];
  period_start: string | null;
  period_end: string | null;
}

export interface ComplaintDetailItemDTO {
  id: string;
  conversation_id: string;
  description: string;
  evidence_quote: string | null;
  severity: string;
  severity_label: string;
  status: string;
  status_label: string;
  guest_name: string | null;
  reported_at: string;
  resolved_at: string | null;
}

export interface ComplaintDetailListResponse {
  property_code: string;
  property_name: string | null;
  category: string;
  category_label: string;
  total_count: number;
  items: ComplaintDetailItemDTO[];
}

export interface GetComplaintHeatmapParams {
  period?: string;
  start_date?: string;
  end_date?: string;
}

// GET /api/v1/complaints/analytics/heatmap
export async function getComplaintHeatmap(
  params?: GetComplaintHeatmapParams
): Promise<ComplaintHeatmapResponse> {
  return apiGet<ComplaintHeatmapResponse>("/complaints/analytics/heatmap", params);
}

// GET /api/v1/complaints/analytics/detail/{property_code}/{category}
export async function getComplaintDetailList(
  propertyCode: string,
  category: string,
  params?: GetComplaintHeatmapParams
): Promise<ComplaintDetailListResponse> {
  return apiGet<ComplaintDetailListResponse>(
    `/complaints/analytics/detail/${propertyCode}/${category}`,
    params
  );
}
