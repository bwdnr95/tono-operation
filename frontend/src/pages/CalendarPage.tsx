// src/pages/CalendarPage.tsx
/**
 * Calendar Page
 * 
 * 숙소별 달력 뷰:
 * - 월간 달력 (예약/차단 현황)
 * - 점유율 표시
 * - iCal 동기화
 */
import React, { useState, useEffect, useCallback } from "react";
import { PageLayout } from "../layout/PageLayout";
import { 
  getCalendar, 
  getPropertiesForCalendar,
  syncIcal,
} from "../api/calendar";
import type { 
  CalendarMonthDTO, 
  CalendarDayDTO,
  PropertyListItem,
} from "../types/calendar";
import { useToast } from "../components/ui/Toast";

// ============================================================
// Helper Functions
// ============================================================

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function getMonthName(month: number): string {
  const names = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];
  return names[month - 1] || "";
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay();
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// ============================================================
// Stat Card Component
// ============================================================

interface StatCardProps {
  icon: string;
  label: string;
  value: string | number;
  unit?: string;
  color?: string;
}

function StatCard({ icon, label, value, unit, color }: StatCardProps) {
  return (
    <div className="stat-card" style={{ minWidth: "140px" }}>
      <div className="stat-card-header">
        <span className="stat-card-icon">{icon}</span>
        <span className="stat-card-label">{label}</span>
      </div>
      <div className="stat-card-value">
        <span className="stat-card-number" style={{ color }}>{value}</span>
        {unit && <span className="stat-card-unit">{unit}</span>}
      </div>
    </div>
  );
}

// ============================================================
// Calendar Grid Component
// ============================================================

interface CalendarGridProps {
  year: number;
  month: number;
  days: CalendarDayDTO[];
  onDayClick?: (day: CalendarDayDTO) => void;
}

function CalendarGrid({ year, month, days, onDayClick }: CalendarGridProps) {
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  
  // 날짜별 데이터 맵
  const dayMap = new Map<string, CalendarDayDTO>();
  days.forEach(d => {
    dayMap.set(d.date, d);
  });
  
  // 그리드 셀 생성
  const cells: (CalendarDayDTO | null)[] = [];
  
  // 빈 셀 (이전 달)
  for (let i = 0; i < firstDay; i++) {
    cells.push(null);
  }
  
  // 날짜 셀
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dayData = dayMap.get(dateStr);
    
    if (dayData) {
      cells.push(dayData);
    } else {
      cells.push({
        date: dateStr,
        type: "available",
        guest_name: null,
        reservation_code: null,
        summary: null,
      });
    }
  }
  
  // 빈 셀 (다음 달)
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  
  const getTypeStyle = (type: string): React.CSSProperties => {
    switch (type) {
      case "reserved":
        return { backgroundColor: "#ef4444", color: "white" };
      case "checkin":
        return { backgroundColor: "#f97316", color: "white" };
      case "checkout":
        return { backgroundColor: "#eab308", color: "white" };
      case "blocked":
        return { backgroundColor: "#6b7280", color: "white" };
      default:
        return { backgroundColor: "var(--border)" };
    }
  };
  
  const getTypeLabel = (type: string): string => {
    switch (type) {
      case "reserved": return "예약";
      case "checkin": return "체크인";
      case "checkout": return "체크아웃";
      case "blocked": return "차단";
      default: return "";
    }
  };
  
  return (
    <div className="calendar-grid">
      {/* 요일 헤더 */}
      <div className="calendar-header">
        {WEEKDAYS.map((day, idx) => (
          <div 
            key={day} 
            className="calendar-weekday"
            style={{ 
              color: idx === 0 ? "#ef4444" : idx === 6 ? "#3b82f6" : undefined 
            }}
          >
            {day}
          </div>
        ))}
      </div>
      
      {/* 날짜 그리드 */}
      <div className="calendar-body">
        {cells.map((cell, idx) => {
          if (!cell) {
            return <div key={idx} className="calendar-cell calendar-cell-empty" />;
          }
          
          const dayNum = new Date(cell.date).getDate();
          const isToday = cell.date === new Date().toISOString().split("T")[0];
          const dayOfWeek = (firstDay + dayNum - 1) % 7;
          
          return (
            <div 
              key={idx}
              className={`calendar-cell ${cell.type !== "available" ? "calendar-cell-occupied" : ""} ${isToday ? "calendar-cell-today" : ""}`}
              style={getTypeStyle(cell.type)}
              onClick={() => onDayClick?.(cell)}
              title={cell.guest_name || cell.summary || getTypeLabel(cell.type) || "예약 가능"}
            >
              <span 
                className="calendar-day-number"
                style={{ 
                  color: cell.type !== "available" ? "inherit" : (dayOfWeek === 0 ? "#ef4444" : dayOfWeek === 6 ? "#3b82f6" : undefined)
                }}
              >
                {dayNum}
              </span>
              {cell.guest_name && (
                <span className="calendar-guest-name">{cell.guest_name}</span>
              )}
              {cell.type === "blocked" && cell.summary && (
                <span className="calendar-guest-name">{cell.summary.slice(0, 8)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// Legend Component
// ============================================================

function CalendarLegend() {
  const items = [
    { color: "var(--border)", label: "예약 가능", textColor: "var(--text-secondary)" },
    { color: "#f97316", label: "체크인" },
    { color: "#ef4444", label: "예약중" },
    { color: "#6b7280", label: "차단" },
  ];
  
  return (
    <div className="calendar-legend">
      {items.map(item => (
        <div key={item.label} className="calendar-legend-item">
          <span 
            className="calendar-legend-dot"
            style={{ backgroundColor: item.color }}
          />
          <span style={{ color: item.textColor || "var(--text)" }}>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

// ============================================================
// Main Page Component
// ============================================================

export default function CalendarPage() {
  // State
  const [properties, setProperties] = useState<PropertyListItem[]>([]);
  const [selectedProperty, setSelectedProperty] = useState<string>("");
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [month, setMonth] = useState<number>(new Date().getMonth() + 1);
  const [calendarData, setCalendarData] = useState<CalendarMonthDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [selectedDay, setSelectedDay] = useState<CalendarDayDTO | null>(null);
  
  const { showToast } = useToast();
  
  // Fetch properties
  useEffect(() => {
    async function fetchProperties() {
      try {
        const data = await getPropertiesForCalendar();
        setProperties(data);
        if (data.length > 0 && !selectedProperty) {
          setSelectedProperty(data[0].property_code);
        }
      } catch (e: any) {
        showToast({ type: "error", title: "숙소 목록 로딩 실패", message: e.message });
      }
    }
    fetchProperties();
  }, []);
  
  // Fetch calendar
  const fetchCalendar = useCallback(async () => {
    if (!selectedProperty) return;
    
    setLoading(true);
    try {
      const data = await getCalendar(selectedProperty, { year, month });
      setCalendarData(data);
    } catch (e: any) {
      showToast({ type: "error", title: "달력 로딩 실패", message: e.message });
    } finally {
      setLoading(false);
    }
  }, [selectedProperty, year, month, showToast]);
  
  useEffect(() => {
    fetchCalendar();
  }, [fetchCalendar]);
  
  // Month navigation
  const goToPrevMonth = () => {
    if (month === 1) {
      setYear(year - 1);
      setMonth(12);
    } else {
      setMonth(month - 1);
    }
  };
  
  const goToNextMonth = () => {
    if (month === 12) {
      setYear(year + 1);
      setMonth(1);
    } else {
      setMonth(month + 1);
    }
  };
  
  const goToToday = () => {
    const now = new Date();
    setYear(now.getFullYear());
    setMonth(now.getMonth() + 1);
  };
  
  // iCal sync
  const handleSync = async () => {
    if (!selectedProperty) return;
    
    setSyncing(true);
    try {
      await syncIcal(selectedProperty);
      showToast({ type: "success", title: "동기화 시작됨" });
      // 백그라운드 동기화 완료 대기 후 달력 새로고침
      setTimeout(() => {
        fetchCalendar();
        setSyncing(false);
      }, 3000);
    } catch (e: any) {
      showToast({ type: "error", title: "동기화 실패", message: e.message });
      setSyncing(false);
    }
  };
  
  // Day click
  const handleDayClick = (day: CalendarDayDTO) => {
    setSelectedDay(day);
  };
  
  const currentProperty = properties.find(p => p.property_code === selectedProperty);
  
  return (
    <PageLayout>
      <div className="calendar-page-wrapper" style={{ padding: "24px 32px" }}>
        {/* Header */}
        <header className="page-header calendar-page-header" style={{ marginBottom: "24px" }}>
          <div className="page-header-content">
            <div>
              <h1 className="page-title">📅 달력</h1>
              <p className="page-subtitle">숙소별 예약 현황</p>
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <select
                value={selectedProperty}
                onChange={(e) => setSelectedProperty(e.target.value)}
                className="select"
                style={{ minWidth: "200px" }}
              >
                {properties.map(p => (
                  <option key={p.property_code} value={p.property_code}>
                    {p.name} ({p.property_code})
                  </option>
                ))}
              </select>
              <button 
                onClick={handleSync} 
                disabled={syncing || !currentProperty?.has_ical}
                className="btn btn-secondary"
                title={!currentProperty?.has_ical ? "iCal URL이 설정되지 않았습니다" : "iCal 동기화"}
              >
                {syncing ? "⟳" : "🔄"}
              </button>
            </div>
          </div>
        </header>
        
        {/* iCal 상태 */}
        {currentProperty && !currentProperty.has_ical && (
          <div className="card" style={{ 
            padding: "12px 16px", 
            marginBottom: "16px", 
            background: "#fef3c7", 
            borderColor: "#f59e0b" 
          }}>
            <span style={{ color: "#92400e" }}>
              ⚠️ iCal URL이 설정되지 않았습니다. 숙소 관리에서 설정하세요.
            </span>
          </div>
        )}
        
        {/* 점유율 요약 */}
        {calendarData && (
          <div className="calendar-stats" style={{ marginBottom: "24px", display: "flex", gap: "16px", flexWrap: "wrap" }}>
            <StatCard 
              icon="📊"
              label="점유율"
              value={calendarData.occupancy_rate.toFixed(1)}
              unit="%"
              color={calendarData.occupancy_rate >= 70 ? "#10b981" : calendarData.occupancy_rate >= 40 ? "#f59e0b" : "#ef4444"}
            />
            <StatCard 
              icon="✅"
              label="예약"
              value={calendarData.reserved_days}
              unit="일"
            />
            <StatCard 
              icon="🚫"
              label="차단"
              value={calendarData.blocked_days}
              unit="일"
            />
            <StatCard 
              icon="⭕"
              label="예약 가능"
              value={calendarData.available_days}
              unit="일"
            />
          </div>
        )}
        
        {/* 달력 */}
        <div className="card" style={{ padding: "20px" }}>
          {/* 월 네비게이션 */}
          <div className="calendar-nav" style={{ 
            display: "flex", 
            justifyContent: "space-between", 
            alignItems: "center",
            marginBottom: "16px"
          }}>
            <button onClick={goToPrevMonth} className="btn btn-secondary calendar-nav-prev">
              ←
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <h2 className="calendar-nav-month" style={{ fontSize: "20px", fontWeight: 600, margin: 0 }}>
                {year}년 {getMonthName(month)}
              </h2>
              <button onClick={goToToday} className="btn btn-secondary calendar-nav-today" style={{ fontSize: "12px", padding: "4px 8px" }}>
                오늘
              </button>
            </div>
            <button onClick={goToNextMonth} className="btn btn-secondary calendar-nav-next">
              →
            </button>
          </div>
          
          {/* 범례 */}
          <CalendarLegend />
          
          {/* 로딩 */}
          {loading && (
            <div style={{ 
              display: "flex", 
              justifyContent: "center", 
              alignItems: "center",
              height: "300px",
              color: "var(--text-muted)"
            }}>
              로딩 중...
            </div>
          )}
          
          {/* 달력 그리드 */}
          {!loading && calendarData && (
            <CalendarGrid
              year={year}
              month={month}
              days={calendarData.days}
              onDayClick={handleDayClick}
            />
          )}
        </div>
        
        {/* 선택된 날짜 상세 */}
        {selectedDay && selectedDay.type !== "available" && (
          <div className="card" style={{ marginTop: "16px", padding: "16px" }}>
            <h3 style={{ fontSize: "14px", fontWeight: 600, marginBottom: "8px" }}>
              📋 {selectedDay.date}
            </h3>
            <div style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
              {selectedDay.type === "reserved" || selectedDay.type === "checkin" ? (
                <>
                  <div>상태: {selectedDay.type === "checkin" ? "체크인" : "예약중"}</div>
                  {selectedDay.guest_name && <div>게스트: {selectedDay.guest_name}</div>}
                  {selectedDay.reservation_code && <div>예약코드: {selectedDay.reservation_code}</div>}
                </>
              ) : selectedDay.type === "blocked" ? (
                <>
                  <div>상태: 차단됨</div>
                  {selectedDay.summary && <div>사유: {selectedDay.summary}</div>}
                </>
              ) : null}
            </div>
            <button 
              onClick={() => setSelectedDay(null)}
              className="btn btn-secondary"
              style={{ marginTop: "12px", fontSize: "12px" }}
            >
              닫기
            </button>
          </div>
        )}
        
        {/* 마지막 동기화 시간 */}
        {currentProperty?.last_synced_at && (
          <div style={{ 
            marginTop: "16px", 
            fontSize: "12px", 
            color: "var(--text-muted)",
            textAlign: "right"
          }}>
            마지막 동기화: {new Date(currentProperty.last_synced_at).toLocaleString("ko-KR")}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
