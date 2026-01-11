// src/pages/AnalyticsPage.tsx
/**
 * Analytics Page
 * 
 * 운영 성과 분석:
 * - 기간별 핵심 지표 (예약 확정, 메시지 발송, 응답 시간, AI 채택률)
 * - 수익 지표 (리드타임, ADR, 점유율)
 * - 월별 트렌드 차트
 * - 숙소별 비교
 * - OC (운영 약속) 분석
 * - Complaint (게스트 불만) 분석
 */
import React, { useState, useEffect, useCallback } from "react";
import { PageLayout } from "../layout/PageLayout";
import { 
  getAnalyticsSummary, 
  getAnalyticsTrend, 
  getAnalyticsByProperty,
  getOCSummary,
  getOCTrend,
  getComplaintHeatmap,
  getComplaintDetailList,
} from "../api/analytics";
import type { 
  AnalyticsSummaryDTO, 
  TrendItemDTO, 
  PropertyComparisonDTO,
  PeriodType,
  OCSummaryDTO,
  OCTrendItemDTO,
  ComplaintHeatmapResponse,
  ComplaintDetailListResponse,
} from "../api/analytics";
import { SkeletonAnalyticsPage } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { useNavigate } from "react-router-dom";

// ============================================================
// Stat Card Component
// ============================================================

interface StatCardProps {
  icon: string;
  label: string;
  value: string | number;
  unit?: string;
  change?: number | null;
  changeLabel?: string;
  changeType?: "percent" | "diff" | "inverse"; // inverse: 낮을수록 좋음 (응답시간)
}

function StatCard({ icon, label, value, unit, change, changeLabel, changeType = "percent" }: StatCardProps) {
  const hasChange = change !== null && change !== undefined;
  
  let isPositive = change && change > 0;
  if (changeType === "inverse") {
    isPositive = change && change < 0; // 응답시간은 낮을수록 좋음
  }
  
  const changeColor = isPositive ? "var(--success)" : change && change < 0 ? "var(--danger)" : "var(--text-muted)";
  const arrow = change && change > 0 ? "↑" : change && change < 0 ? "↓" : "─";
  
  return (
    <div className="stat-card">
      <div className="stat-card-header">
        <span className="stat-card-icon">{icon}</span>
        <span className="stat-card-label">{label}</span>
      </div>
      <div className="stat-card-value">
        <span className="stat-card-number">{value}</span>
        {unit && <span className="stat-card-unit">{unit}</span>}
      </div>
      {hasChange && (
        <div className="stat-card-change" style={{ color: changeColor }}>
          <span>{arrow} {Math.abs(change)}{changeType === "percent" ? "%" : changeType === "diff" ? "" : ""}</span>
          {changeLabel && <span className="stat-card-change-label">{changeLabel}</span>}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Bar Chart Component (CSS only)
// ============================================================

interface BarChartProps {
  data: { label: string; value1: number; value2: number }[];
  legend1: string;
  legend2: string;
  color1?: string;
  color2?: string;
}

function BarChart({ data, legend1, legend2, color1 = "var(--primary)", color2 = "var(--success)" }: BarChartProps) {
  const maxValue = Math.max(...data.flatMap(d => [d.value1, d.value2]), 1);
  
  return (
    <div className="bar-chart">
      <div className="bar-chart-legend">
        <span className="legend-item">
          <span className="legend-dot" style={{ background: color1 }} />
          {legend1}
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: color2 }} />
          {legend2}
        </span>
      </div>
      <div className="bar-chart-body">
        {data.map((item, idx) => (
          <div key={idx} className="bar-chart-group">
            <div className="bar-chart-bars">
              <div 
                className="bar-chart-bar"
                style={{ 
                  height: `${(item.value1 / maxValue) * 100}%`,
                  background: color1 
                }}
                title={`${legend1}: ${item.value1}`}
              >
                {item.value1 > 0 && <span className="bar-value">{item.value1}</span>}
              </div>
              <div 
                className="bar-chart-bar"
                style={{ 
                  height: `${(item.value2 / maxValue) * 100}%`,
                  background: color2 
                }}
                title={`${legend2}: ${item.value2}`}
              >
                {item.value2 > 0 && <span className="bar-value">{item.value2}</span>}
              </div>
            </div>
            <span className="bar-chart-label">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Line Chart Component (CSS only)
// ============================================================

interface LineChartProps {
  data: { label: string; value: number | null }[];
  color?: string;
  unit?: string;
}

function LineChart({ data, color = "var(--primary)", unit = "" }: LineChartProps) {
  const values = data.map(d => d.value).filter((v): v is number => v !== null);
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const range = maxValue - minValue || 1;
  
  return (
    <div className="line-chart">
      <div className="line-chart-body">
        {data.map((item, idx) => {
          const height = item.value !== null 
            ? ((item.value - minValue) / range) * 100 
            : 0;
          
          return (
            <div key={idx} className="line-chart-point-wrapper">
              <div 
                className="line-chart-point"
                style={{ 
                  bottom: `${height}%`,
                  background: color,
                }}
                title={item.value !== null ? `${item.value}${unit}` : "N/A"}
              >
                {item.value !== null && (
                  <span className="line-chart-value">{item.value}{unit}</span>
                )}
              </div>
              <span className="line-chart-label">{item.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// Main Page Component
// ============================================================

export default function AnalyticsPage() {
  // State
  const [period, setPeriod] = useState<PeriodType>("month");
  const [customStartDate, setCustomStartDate] = useState<string>("");
  const [customEndDate, setCustomEndDate] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [summary, setSummary] = useState<AnalyticsSummaryDTO | null>(null);
  const [trend, setTrend] = useState<TrendItemDTO[]>([]);
  const [byProperty, setByProperty] = useState<PropertyComparisonDTO[]>([]);
  
  // OC Analytics state
  const [ocSummary, setOcSummary] = useState<OCSummaryDTO | null>(null);
  const [ocTrend, setOcTrend] = useState<OCTrendItemDTO[]>([]);
  
  // Complaint 히트맵 state
  const [complaintHeatmap, setComplaintHeatmap] = useState<ComplaintHeatmapResponse | null>(null);
  const [complaintPeriod, setComplaintPeriod] = useState<string>("month");
  
  // Complaint 상세 모달
  const [complaintDetailModal, setComplaintDetailModal] = useState<{
    open: boolean;
    propertyCode: string;
    propertyName: string;
    category: string;
  } | null>(null);
  const [complaintDetailData, setComplaintDetailData] = useState<ComplaintDetailListResponse | null>(null);
  const [complaintDetailLoading, setComplaintDetailLoading] = useState(false);
  
  // 테이블 정렬
  type SortKey = "reservations_confirmed" | "messages_sent" | "lead_time_days" | "adr" | "occupancy_rate";
  const [sortKey, setSortKey] = useState<SortKey>("reservations_confirmed");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  
  const { showToast } = useToast();
  const navigate = useNavigate();
  
  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const params: { 
        period: PeriodType; 
        start_date?: string; 
        end_date?: string; 
      } = { period };
      
      // Custom 기간일 때 날짜 추가
      if (period === "custom" && customStartDate && customEndDate) {
        params.start_date = customStartDate;
        params.end_date = customEndDate;
      }
      
      const [summaryRes, trendRes, propertyRes, ocSummaryRes, ocTrendRes, complaintHeatmapRes] = await Promise.all([
        getAnalyticsSummary(params),
        getAnalyticsTrend({ months: 6 }),
        getAnalyticsByProperty(params),
        getOCSummary(params),
        getOCTrend({ months: 6 }),
        getComplaintHeatmap({ period: "month" }),
      ]);
      
      setSummary(summaryRes);
      setTrend(trendRes.items);
      setByProperty(propertyRes.items);
      setOcSummary(ocSummaryRes);
      setOcTrend(ocTrendRes.items);
      setComplaintHeatmap(complaintHeatmapRes);
    } catch (e: any) {
      const errorMsg = e?.message || "데이터를 불러오는 중 오류가 발생했습니다";
      setError(errorMsg);
      showToast({ type: "error", title: "데이터 로딩 실패", message: errorMsg });
    } finally {
      setLoading(false);
    }
  }, [period, customStartDate, customEndDate, showToast]);
  
  useEffect(() => {
    // custom이면 날짜가 둘 다 있을 때만 fetch
    if (period === "custom") {
      if (customStartDate && customEndDate) {
        fetchData();
      }
    } else {
      fetchData();
    }
  }, [period, customStartDate, customEndDate, fetchData]);
  
  // Complaint 히트맵 기간 변경
  const handleComplaintPeriodChange = async (newPeriod: string) => {
    setComplaintPeriod(newPeriod);
    try {
      const res = await getComplaintHeatmap({ period: newPeriod });
      setComplaintHeatmap(res);
    } catch (e: any) {
      showToast({ type: "error", title: "히트맵 로딩 실패", message: e?.message || "오류 발생" });
    }
  };
  
  // Complaint 히트맵 셀 클릭 → 상세 모달
  const handleComplaintCellClick = async (propertyCode: string, propertyName: string, category: string) => {
    setComplaintDetailModal({ open: true, propertyCode, propertyName, category });
    setComplaintDetailLoading(true);
    setComplaintDetailData(null);
    
    try {
      const data = await getComplaintDetailList(propertyCode, category, { period: complaintPeriod });
      setComplaintDetailData(data);
    } catch (e: any) {
      showToast({ type: "error", title: "상세 조회 실패", message: e?.message || "오류 발생" });
    } finally {
      setComplaintDetailLoading(false);
    }
  };
  
  // Complaint 상세 모달 닫기
  const closeComplaintDetailModal = () => {
    setComplaintDetailModal(null);
    setComplaintDetailData(null);
  };
  
  // 대화로 이동
  const goToConversation = (conversationId: string) => {
    navigate(`/inbox?conversation_id=${conversationId}`);
  };
  
  // Format helpers
  const formatCurrency = (value: number | null) => {
    if (value === null) return "-";
    return `₩${value.toLocaleString()}`;
  };
  
  const formatMinutes = (value: number | null) => {
    if (value === null) return "-";
    if (value < 60) return `${Math.round(value)}분`;
    const hours = Math.floor(value / 60);
    const mins = Math.round(value % 60);
    return `${hours}시간 ${mins}분`;
  };
  
  const formatDays = (value: number | null) => {
    if (value === null) return "-";
    return `${Math.round(value)}일`;
  };
  
  const formatPercent = (value: number | null) => {
    if (value === null) return "-";
    return `${value}%`;
  };
  
  // 테이블 정렬 핸들러
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      // 같은 컬럼 클릭 → 방향 토글
      setSortDir(prev => prev === "asc" ? "desc" : "asc");
    } else {
      // 다른 컬럼 클릭 → 내림차순으로 시작
      setSortKey(key);
      setSortDir("desc");
    }
  };
  
  // 정렬된 숙소 데이터
  const sortedByProperty = [...byProperty].sort((a, b) => {
    const aVal = a[sortKey] ?? -Infinity;
    const bVal = b[sortKey] ?? -Infinity;
    const diff = (aVal as number) - (bVal as number);
    return sortDir === "asc" ? diff : -diff;
  });
  
  // 정렬 아이콘
  const getSortIcon = (key: SortKey) => {
    if (sortKey !== key) return "↕";
    return sortDir === "asc" ? "↑" : "↓";
  };
  
  // Trend chart data
  const trendChartData = trend.map(t => ({
    label: t.month.slice(5), // "2025-12" -> "12"
    value1: t.reservations_confirmed,
    value2: t.messages_sent,
  }));
  
  const aiAdoptionData = trend.map(t => ({
    label: t.month.slice(5),
    value: t.ai_adoption_rate,
  }));
  
  const adrData = trend.map(t => ({
    label: t.month.slice(5),
    value: t.adr ? Math.round(t.adr / 10000) : null, // 만원 단위
  }));
  
  return (
    <PageLayout>
      <div style={{ padding: "24px 32px" }}>
        {/* Header */}
        <header className="page-header" style={{ marginBottom: "24px" }}>
          <div className="page-header-content">
            <div>
              <h1 className="page-title">📊 Analytics</h1>
              <p className="page-subtitle">운영 성과 분석</p>
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <select 
                value={period} 
                onChange={(e) => setPeriod(e.target.value as PeriodType)}
                className="select"
              >
                <option value="today">오늘</option>
                <option value="week">이번 주</option>
                <option value="month">이번 달</option>
                <option value="custom">기간 선택</option>
              </select>
              {period === "custom" && (
                <>
                  <input
                    type="date"
                    value={customStartDate}
                    onChange={(e) => setCustomStartDate(e.target.value)}
                    className="input"
                    style={{ width: "140px" }}
                  />
                  <span style={{ color: "var(--text-muted)" }}>~</span>
                  <input
                    type="date"
                    value={customEndDate}
                    onChange={(e) => setCustomEndDate(e.target.value)}
                    className="input"
                    style={{ width: "140px" }}
                  />
                </>
              )}
              <button onClick={fetchData} disabled={loading} className="btn btn-secondary">
                {loading ? "로딩..." : "새로고침"}
              </button>
            </div>
          </div>
        </header>
        
        {/* Error */}
        {error && !loading && (
          <div className="card" style={{ padding: "16px", marginBottom: "24px", background: "var(--danger-bg)", borderColor: "var(--danger)" }}>
            <span style={{ color: "var(--danger)" }}>{error}</span>
          </div>
        )}
        
        {/* Loading - 스켈레톤 */}
        {loading && (
          <SkeletonAnalyticsPage />
        )}
        
        {/* Content */}
        {!loading && summary && (
          <>
            {/* 기간 정보 */}
            <div style={{ marginBottom: "16px", fontSize: "13px", color: "var(--text-muted)" }}>
              {summary.start_date} ~ {summary.end_date}
            </div>
            
            {/* 운영 지표 */}
            <div style={{ marginBottom: "24px" }}>
              <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "12px" }}>📈 운영 지표</h2>
              <div className="stat-grid">
                <StatCard 
                  icon="📋"
                  label="예약 확정"
                  value={summary.reservations_confirmed}
                  unit="건"
                  change={summary.reservations_confirmed_change}
                  changeLabel="이전 기간 대비"
                />
                <StatCard 
                  icon="💬"
                  label="메시지 발송"
                  value={summary.messages_sent}
                  unit="건"
                  change={summary.messages_sent_change}
                  changeLabel="이전 기간 대비"
                />
                <StatCard 
                  icon="⏱️"
                  label="평균 응답 시간"
                  value={formatMinutes(summary.avg_response_minutes)}
                  change={summary.avg_response_change}
                  changeType="inverse"
                  changeLabel="분"
                />
                <StatCard 
                  icon="🤖"
                  label="AI 채택률"
                  value={formatPercent(summary.ai_adoption_rate)}
                  change={summary.ai_adoption_change}
                  changeType="diff"
                  changeLabel="%p"
                />
              </div>
            </div>
            
            {/* 수익 지표 */}
            <div style={{ marginBottom: "24px" }}>
              <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "12px" }}>💰 수익 지표</h2>
              <div className="stat-grid">
                <StatCard 
                  icon="📅"
                  label="예약 리드타임"
                  value={formatDays(summary.lead_time_days)}
                />
                <StatCard 
                  icon="💵"
                  label="ADR"
                  value={formatCurrency(summary.adr)}
                />
                <StatCard 
                  icon="📊"
                  label="점유율"
                  value={summary.occupancy_rate !== null ? formatPercent(summary.occupancy_rate) : "연동 필요"}
                />
              </div>
            </div>
            
            {/* 월별 트렌드 */}
            <div style={{ marginBottom: "24px" }}>
              <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "12px" }}>📊 월별 트렌드</h2>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div className="card" style={{ padding: "16px" }}>
                  <h3 style={{ fontSize: "14px", fontWeight: 500, marginBottom: "12px" }}>예약 확정 & 메시지 발송</h3>
                  <BarChart 
                    data={trendChartData}
                    legend1="예약 확정"
                    legend2="메시지 발송"
                  />
                </div>
                <div className="card" style={{ padding: "16px" }}>
                  <h3 style={{ fontSize: "14px", fontWeight: 500, marginBottom: "12px" }}>AI 채택률 (%)</h3>
                  <LineChart 
                    data={aiAdoptionData}
                    color="var(--primary)"
                    unit="%"
                  />
                </div>
              </div>
            </div>
            
            {/* 숙소별 비교 */}
            {byProperty.length > 0 && (
              <div>
                <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "12px" }}>📋 숙소별 비교</h2>
                <div className="card" style={{ overflow: "auto" }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>숙소</th>
                        <th 
                          onClick={() => handleSort("reservations_confirmed")}
                          className="sortable-header"
                          style={{ textAlign: "right", cursor: "pointer" }}
                        >
                          예약 확정 {getSortIcon("reservations_confirmed")}
                        </th>
                        <th 
                          onClick={() => handleSort("messages_sent")}
                          className="sortable-header"
                          style={{ textAlign: "right", cursor: "pointer" }}
                        >
                          메시지 발송 {getSortIcon("messages_sent")}
                        </th>
                        <th 
                          onClick={() => handleSort("lead_time_days")}
                          className="sortable-header"
                          style={{ textAlign: "right", cursor: "pointer" }}
                        >
                          리드타임 {getSortIcon("lead_time_days")}
                        </th>
                        <th 
                          onClick={() => handleSort("adr")}
                          className="sortable-header"
                          style={{ textAlign: "right", cursor: "pointer" }}
                        >
                          ADR {getSortIcon("adr")}
                        </th>
                        <th 
                          onClick={() => handleSort("occupancy_rate")}
                          className="sortable-header"
                          style={{ textAlign: "right", cursor: "pointer" }}
                        >
                          점유율 {getSortIcon("occupancy_rate")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedByProperty.map((item) => (
                        <tr key={item.property_code}>
                          <td>
                            <div style={{ fontWeight: 500 }}>{item.property_name || item.property_code}</div>
                            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>{item.property_code}</div>
                          </td>
                          <td style={{ textAlign: "right" }}>{item.reservations_confirmed}건</td>
                          <td style={{ textAlign: "right" }}>{item.messages_sent}건</td>
                          <td style={{ textAlign: "right" }}>{formatDays(item.lead_time_days)}</td>
                          <td style={{ textAlign: "right" }}>{formatCurrency(item.adr)}</td>
                          <td style={{ textAlign: "right", color: item.occupancy_rate === null ? "var(--text-muted)" : undefined }}>
                            {item.occupancy_rate !== null ? formatPercent(item.occupancy_rate) : "연동 필요"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            
            {/* ═══════════════════════════════════════════════════════════════════
                OC Analytics (운영 약속 분석)
            ════════════════════════════════════════════════════════════════════ */}
            {ocSummary && (
              <>
                {/* OC 요약 지표 */}
                <div style={{ marginTop: "32px", marginBottom: "24px" }}>
                  <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "16px" }}>
                    🎯 운영 약속 (OC) 분석
                  </h2>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px" }}>
                    <StatCard
                      icon="📋"
                      label="OC 발생"
                      value={ocSummary.total_count}
                      unit="건"
                      change={ocSummary.total_count_change}
                      changeLabel="이전 기간 대비"
                    />
                    <StatCard
                      icon="✅"
                      label="완료 건수"
                      value={ocSummary.completed_count}
                      unit="건"
                    />
                    <StatCard
                      icon="📊"
                      label="완료율"
                      value={ocSummary.completion_rate ?? "-"}
                      unit={ocSummary.completion_rate !== null ? "%" : ""}
                    />
                  </div>
                </div>
                
                {/* OC Topic별 분포 */}
                {ocSummary.by_topic.length > 0 && (
                  <div className="card" style={{ marginBottom: "24px" }}>
                    <div className="card-header">
                      <h3 className="card-title">유형별 분포</h3>
                    </div>
                    <div className="card-body">
                      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                        {ocSummary.by_topic.map((item) => (
                          <div key={item.topic} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                            <div style={{ width: "120px", fontSize: "14px", fontWeight: 500 }}>
                              {item.topic_label}
                            </div>
                            <div style={{ flex: 1, height: "24px", background: "var(--bg-secondary)", borderRadius: "4px", overflow: "hidden" }}>
                              <div 
                                style={{ 
                                  width: `${item.percentage}%`, 
                                  height: "100%", 
                                  background: "var(--primary)",
                                  borderRadius: "4px",
                                  transition: "width 0.3s ease",
                                }} 
                              />
                            </div>
                            <div style={{ width: "80px", textAlign: "right", fontSize: "14px" }}>
                              {item.count}건 ({item.percentage}%)
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                
                {/* OC 월별 트렌드 */}
                {ocTrend.length > 0 && (
                  <div className="card" style={{ marginBottom: "24px" }}>
                    <div className="card-header">
                      <h3 className="card-title">OC 월별 트렌드</h3>
                    </div>
                    <div className="card-body">
                      <BarChart
                        data={ocTrend.map(t => ({
                          label: t.month.slice(5),
                          value1: t.total_count,
                          value2: t.completed_count,
                        }))}
                        legend1="OC 발생"
                        legend2="완료"
                        color1="var(--warning)"
                      />
                    </div>
                  </div>
                )}
                
                {/* 현재 OC 현황 (전체 기준) */}
                {ocSummary.by_status.length > 0 && (
                  <div className="card" style={{ marginBottom: "24px" }}>
                    <div className="card-header">
                      <h3 className="card-title">현재 OC 현황</h3>
                      <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>전체 기간 기준</span>
                    </div>
                    <div className="card-body">
                      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                        {ocSummary.by_status.map((item) => {
                          // 상태별 색상
                          const statusColors: Record<string, string> = {
                            pending: "#ef4444",      // 빨강 (대기 중)
                            done: "#22c55e",         // 초록 (완료)
                            resolved: "#3b82f6",     // 파랑 (해소됨)
                            suggested_resolve: "#f59e0b", // 주황 (해소 제안)
                          };
                          const borderColor = statusColors[item.status] || "var(--border)";
                          
                          return (
                            <div 
                              key={item.status} 
                              style={{ 
                                padding: "16px 24px", 
                                background: "var(--bg-secondary)", 
                                borderRadius: "8px",
                                textAlign: "center",
                                minWidth: "120px",
                                borderLeft: `4px solid ${borderColor}`,
                              }}
                            >
                              <div style={{ fontSize: "28px", fontWeight: 600 }}>{item.count}</div>
                              <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>{item.status_label}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
                
                {/* 숙소별 Complaint 발생 히트맵 */}
                {complaintHeatmap && (
                  <div className="card" style={{ marginBottom: "24px" }}>
                    <div className="card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <h3 className="card-title">🔴 숙소별 Complaint 현황</h3>
                        <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                          게스트 불만/문제 발생 현황 · 셀 클릭 시 상세 보기
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: "8px" }}>
                        {["week", "month", "quarter", "year", "all"].map((p) => (
                          <button
                            key={p}
                            onClick={() => handleComplaintPeriodChange(p)}
                            style={{
                              padding: "4px 12px",
                              fontSize: "12px",
                              border: "1px solid var(--border)",
                              borderRadius: "4px",
                              background: complaintPeriod === p ? "var(--primary)" : "var(--surface)",
                              color: complaintPeriod === p ? "white" : "var(--text)",
                              cursor: "pointer",
                            }}
                          >
                            {p === "week" ? "1주" : p === "month" ? "1개월" : p === "quarter" ? "3개월" : p === "year" ? "1년" : "전체"}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="card-body" style={{ overflowX: "auto" }}>
                      {complaintHeatmap.rows.length > 0 ? (
                        <>
                          <table className="table" style={{ minWidth: "600px" }}>
                            <thead>
                              <tr>
                                <th style={{ textAlign: "left", minWidth: "150px" }}>숙소</th>
                                {complaintHeatmap.categories.map(category => (
                                  <th key={category} style={{ textAlign: "center", minWidth: "80px" }}>
                                    {complaintHeatmap.category_labels[category] || category}
                                  </th>
                                ))}
                                <th style={{ textAlign: "center", minWidth: "60px" }}>총합</th>
                              </tr>
                            </thead>
                            <tbody>
                              {complaintHeatmap.rows.map((row) => (
                                <tr key={row.property_code}>
                                  <td>
                                    <div style={{ fontWeight: 500 }}>{row.property_name || row.property_code}</div>
                                    <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>{row.property_code}</div>
                                  </td>
                                  {row.cells.map((cell) => {
                                    // 건수별 색상 (히트맵)
                                    let bgColor = "transparent";
                                    let textColor = "var(--text-muted)";
                                    if (cell.count >= 5) {
                                      bgColor = "#fee2e2"; textColor = "#dc2626"; // 빨강
                                    } else if (cell.count >= 2) {
                                      bgColor = "#fef3c7"; textColor = "#d97706"; // 주황
                                    } else if (cell.count >= 1) {
                                      bgColor = "#dcfce7"; textColor = "#16a34a"; // 초록
                                    }
                                    
                                    return (
                                      <td 
                                        key={cell.category}
                                        onClick={() => cell.count > 0 && handleComplaintCellClick(row.property_code, row.property_name || row.property_code, cell.category)}
                                        style={{ 
                                          textAlign: "center",
                                          background: bgColor,
                                          color: textColor,
                                          fontWeight: cell.count > 0 ? 600 : 400,
                                          cursor: cell.count > 0 ? "pointer" : "default",
                                          transition: "all 0.2s",
                                        }}
                                      >
                                        {cell.count > 0 ? cell.count : "-"}
                                      </td>
                                    );
                                  })}
                                  <td style={{ textAlign: "center", fontWeight: 600 }}>{row.total_count}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          
                          {/* 범례 */}
                          <div style={{ marginTop: "16px", display: "flex", gap: "16px", fontSize: "12px" }}>
                            <span><span style={{ display: "inline-block", width: "12px", height: "12px", background: "#fee2e2", marginRight: "4px", borderRadius: "2px" }}></span> 5건 이상</span>
                            <span><span style={{ display: "inline-block", width: "12px", height: "12px", background: "#fef3c7", marginRight: "4px", borderRadius: "2px" }}></span> 2~4건</span>
                            <span><span style={{ display: "inline-block", width: "12px", height: "12px", background: "#dcfce7", marginRight: "4px", borderRadius: "2px" }}></span> 1건</span>
                          </div>
                        </>
                      ) : (
                        <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                          해당 기간에 Complaint가 없습니다
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
      
      {/* Complaint 상세 모달 */}
      {complaintDetailModal && (
        <div 
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "var(--overlay)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={closeComplaintDetailModal}
        >
          <div 
            style={{
              background: "var(--surface)",
              borderRadius: "12px",
              width: "90%",
              maxWidth: "800px",
              maxHeight: "80vh",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 모달 헤더 */}
            <div style={{ 
              padding: "20px 24px", 
              borderBottom: "1px solid var(--border)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 600 }}>
                  {complaintDetailModal.propertyName} &gt; {complaintHeatmap?.category_labels[complaintDetailModal.category] || complaintDetailModal.category}
                </h3>
                <p style={{ margin: "4px 0 0", fontSize: "14px", color: "var(--text-muted)" }}>
                  {complaintDetailData ? `총 ${complaintDetailData.total_count}건` : "로딩 중..."}
                </p>
              </div>
              <button 
                onClick={closeComplaintDetailModal}
                style={{ 
                  background: "none", 
                  border: "none", 
                  fontSize: "24px", 
                  cursor: "pointer",
                  color: "var(--text-muted)",
                }}
              >
                ×
              </button>
            </div>
            
            {/* 모달 바디 */}
            <div style={{ flex: 1, overflow: "auto", padding: "16px 24px" }}>
              {complaintDetailLoading ? (
                <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                  로딩 중...
                </div>
              ) : complaintDetailData && complaintDetailData.items.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {complaintDetailData.items.map((item) => {
                    // severity별 색상 - 다크모드 지원
                    const severityColors: Record<string, { bg: string; text: string; border: string }> = {
                      critical: { bg: "var(--danger-bg)", text: "var(--danger)", border: "var(--danger)" },
                      high: { bg: "var(--danger-bg)", text: "var(--danger)", border: "var(--danger)" },
                      medium: { bg: "var(--warning-bg)", text: "var(--warning)", border: "var(--warning)" },
                      low: { bg: "var(--bg-secondary)", text: "var(--text-secondary)", border: "var(--border)" },
                    };
                    const colors = severityColors[item.severity] || severityColors.medium;
                    
                    return (
                      <div 
                        key={item.id}
                        style={{
                          padding: "16px",
                          background: "var(--bg-secondary)",
                          borderRadius: "8px",
                          borderLeft: `4px solid ${colors.border}`,
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                          <div>
                            <span style={{ 
                              fontSize: "12px", 
                              color: "var(--text-muted)",
                              marginRight: "8px",
                            }}>
                              📅 {new Date(item.reported_at).toLocaleDateString("ko-KR")}
                            </span>
                            {item.guest_name && (
                              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                                👤 {item.guest_name}
                              </span>
                            )}
                          </div>
                          <div style={{ display: "flex", gap: "8px" }}>
                            <span style={{
                              fontSize: "11px",
                              padding: "2px 8px",
                              borderRadius: "4px",
                              background: colors.bg,
                              color: colors.text,
                            }}>
                              {item.severity_label}
                            </span>
                            <span style={{
                              fontSize: "11px",
                              padding: "2px 8px",
                              borderRadius: "4px",
                              background: item.status === "resolved" ? "var(--success-bg)" :
                                          item.status === "in_progress" ? "var(--primary-bg)" :
                                          item.status === "open" ? "var(--danger-bg)" : "var(--bg-secondary)",
                              color: item.status === "resolved" ? "var(--success)" :
                                     item.status === "in_progress" ? "var(--primary)" :
                                     item.status === "open" ? "var(--danger)" : "var(--text-secondary)",
                            }}>
                              {item.status_label}
                            </span>
                          </div>
                        </div>
                        
                        <p style={{ margin: "0 0 8px", fontSize: "14px", fontWeight: 500 }}>
                          {item.description}
                        </p>
                        
                        {item.evidence_quote && (
                          <p style={{ 
                            margin: "0 0 8px", 
                            fontSize: "13px", 
                            color: "var(--text-muted)",
                            fontStyle: "italic",
                            padding: "8px",
                            background: "var(--surface)",
                            borderRadius: "4px",
                          }}>
                            "{item.evidence_quote}"
                          </p>
                        )}
                        
                        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center" }}>
                          <button
                            onClick={() => goToConversation(item.conversation_id)}
                            style={{
                              fontSize: "12px",
                              padding: "4px 12px",
                              background: "var(--primary)",
                              color: "white",
                              border: "none",
                              borderRadius: "4px",
                              cursor: "pointer",
                            }}
                          >
                            대화 보기 →
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                  데이터가 없습니다
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
