// src/pages/BookingRequestsPage.tsx
/**
 * 예약 요청 페이지
 * 
 * InboxPage와 동일한 구조:
 * - 탭: 전체 / 대기중 / 만료됨
 * - 왼쪽 리스트 + 오른쪽 상세 패널
 */
import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { getPendingReservations, declinePendingReservation } from "../api/dashboard";
import type { PendingReservationDTO } from "../types/dashboard";
import { SkeletonConversationList } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";

// ============================================================
// Types
// ============================================================

type TabFilter = "all" | "pending" | "expired";

// ============================================================
// Utility Functions
// ============================================================

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  const d = new Date(dateStr);
  return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;
}

function formatCurrency(amount: number | null): string {
  if (!amount) return "-";
  return `₩${amount.toLocaleString()}`;
}

function formatTime(v: string | null): string {
  if (!v) return "-";
  try {
    return new Date(v).toLocaleString("ko-KR", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return v;
  }
}

function getStatusInfo(remainingHours: number | null): { label: string; className: string } {
  const hours = remainingHours ?? 0;
  
  if (hours <= 0) {
    return { label: "만료됨", className: "badge-danger" };
  } else if (hours <= 6) {
    return { label: `${Math.round(hours)}시간`, className: "badge-danger" };
  } else if (hours <= 12) {
    return { label: `${Math.round(hours)}시간`, className: "badge-warning" };
  } else {
    return { label: `${Math.round(hours)}시간`, className: "badge-success" };
  }
}

// ============================================================
// Detail Panel Component
// ============================================================

interface DetailPanelProps {
  item: PendingReservationDTO | null;
  loading: boolean;
  onDecline?: (id: number) => void;
}

function DetailPanel({ item, loading, onDecline }: DetailPanelProps) {
  if (loading) {
    return (
      <div className="empty-state" style={{ flex: 1 }}>
        <div className="loading-spinner" />
      </div>
    );
  }

  if (!item) {
    return (
      <div className="empty-state" style={{ flex: 1 }}>
        <div className="empty-state-icon">📩</div>
        <div className="empty-state-title">예약 요청을 선택하세요</div>
        <div className="empty-state-text">왼쪽 목록에서 항목을 클릭하면 상세 정보가 표시됩니다</div>
      </div>
    );
  }

  const statusInfo = getStatusInfo(item.remaining_hours);
  const isExpired = (item.remaining_hours ?? 0) <= 0;

  const [showConfirm, setShowConfirm] = useState(false);

  const handleOpenAirbnb = () => {
    if (item.action_url) {
      window.open(item.action_url, "_blank", "noopener,noreferrer");
    }
  };

  const handleDeclineClick = () => {
    setShowConfirm(true);
  };

  const handleConfirmDecline = () => {
    setShowConfirm(false);
    onDecline?.(item.id);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", position: "relative" }}>
      {/* 확인 모달 */}
      {showConfirm && (
        <div 
          style={{
            position: "absolute",
            inset: 0,
            background: "var(--overlay)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            borderRadius: "var(--radius)",
          }}
          onClick={() => setShowConfirm(false)}
        >
          <div 
            style={{
              background: "var(--surface)",
              borderRadius: "12px",
              padding: "24px",
              maxWidth: "360px",
              boxShadow: "var(--shadow-lg)",
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ 
              width: "48px", 
              height: "48px", 
              borderRadius: "50%", 
              background: "var(--danger-bg)", 
              display: "flex", 
              alignItems: "center", 
              justifyContent: "center",
              margin: "0 auto 16px",
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </div>
            <h3 style={{ textAlign: "center", marginBottom: "8px", fontSize: "18px", fontWeight: "600" }}>
              거절 처리 확인
            </h3>
            <p style={{ textAlign: "center", color: "var(--text-secondary)", marginBottom: "24px", lineHeight: "1.5" }}>
              에어비앤비에서 이미 거절하셨나요?<br/>
              확인을 누르면 이 예약 요청이 목록에서 제거됩니다.
            </p>
            <div style={{ display: "flex", gap: "12px" }}>
              <button
                onClick={() => setShowConfirm(false)}
                className="btn"
                style={{ 
                  flex: 1, 
                  padding: "12px",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-color)",
                }}
              >
                취소
              </button>
              <button
                onClick={handleConfirmDecline}
                className="btn"
                style={{ 
                  flex: 1, 
                  padding: "12px",
                  background: "#dc2626",
                  color: "white",
                  border: "none",
                }}
              >
                거절 처리
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="card-header" style={{ borderBottom: "1px solid var(--border-color)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div
            style={{
              width: "48px",
              height: "48px",
              borderRadius: "50%",
              background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontWeight: "600",
              fontSize: "18px",
            }}
          >
            {item.guest_name?.charAt(0) || "?"}
          </div>
          <div>
            <div style={{ fontWeight: "600", fontSize: "18px" }}>{item.guest_name || "게스트"}</div>
            {item.property_code && (
              <span className="badge badge-primary" style={{ marginTop: "4px" }}>
                {item.property_code}
              </span>
            )}
          </div>
        </div>
        <span className={`badge ${statusInfo.className}`} style={{ fontSize: "13px", padding: "6px 12px" }}>
          {isExpired ? "⚠️ 만료됨" : `⏱️ ${statusInfo.label} 남음`}
        </span>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px" }}>
        {/* 예약 정보 */}
        <div style={{ marginBottom: "24px" }}>
          <h3 style={{ fontSize: "14px", fontWeight: "600", color: "var(--text-muted)", marginBottom: "12px" }}>
            예약 정보
          </h3>
          <div style={{ 
            display: "grid", 
            gridTemplateColumns: "1fr 1fr", 
            gap: "16px",
            background: "var(--bg-secondary)",
            borderRadius: "var(--radius)",
            padding: "16px"
          }}>
            <div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>체크인</div>
              <div style={{ fontWeight: "600" }}>{formatDate(item.checkin_date)}</div>
            </div>
            <div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>체크아웃</div>
              <div style={{ fontWeight: "600" }}>{formatDate(item.checkout_date)}</div>
            </div>
            <div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>숙박</div>
              <div style={{ fontWeight: "600" }}>{item.nights || 0}박</div>
            </div>
            <div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>인원</div>
              <div style={{ fontWeight: "600" }}>{item.guest_count || "-"}명</div>
            </div>
          </div>
        </div>

        {/* 게스트 메시지 */}
        {item.guest_message && (
          <div style={{ marginBottom: "24px" }}>
            <h3 style={{ fontSize: "14px", fontWeight: "600", color: "var(--text-muted)", marginBottom: "12px" }}>
              게스트 메시지
            </h3>
            <div style={{ 
              background: "var(--bg-secondary)",
              borderRadius: "var(--radius)",
              padding: "16px",
              fontSize: "14px",
              lineHeight: "1.6",
              whiteSpace: "pre-wrap"
            }}>
              {item.guest_message}
            </div>
          </div>
        )}

        {/* 숙소 정보 */}
        {item.listing_name && (
          <div style={{ marginBottom: "24px" }}>
            <h3 style={{ fontSize: "14px", fontWeight: "600", color: "var(--text-muted)", marginBottom: "12px" }}>
              숙소
            </h3>
            <div style={{ 
              background: "var(--bg-secondary)",
              borderRadius: "var(--radius)",
              padding: "16px",
              fontSize: "14px"
            }}>
              📍 {item.listing_name}
            </div>
          </div>
        )}

        {/* 수익 정보 */}
        <div style={{ marginBottom: "24px" }}>
          <h3 style={{ fontSize: "14px", fontWeight: "600", color: "var(--text-muted)", marginBottom: "12px" }}>
            예상 수익
          </h3>
          <div style={{ 
            background: "linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)",
            borderRadius: "var(--radius)",
            padding: "20px",
            textAlign: "center"
          }}>
            <div style={{ fontSize: "28px", fontWeight: "700", color: "#16a34a" }}>
              {formatCurrency(item.expected_payout)}
            </div>
          </div>
        </div>
      </div>

      {/* Footer - Action Buttons */}
      <div style={{ 
        padding: "16px 24px", 
        borderTop: "1px solid var(--border-color)",
        background: "var(--bg-primary)"
      }}>
        <div style={{ display: "flex", gap: "12px", marginBottom: item.action_url ? "0" : "8px" }}>
          <button
            onClick={handleOpenAirbnb}
            disabled={!item.action_url}
            className="btn btn-primary"
            style={{ 
              flex: 1,
              padding: "14px",
              background: item.action_url ? "#ff385c" : "#d1d5db",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px"
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15,3 21,3 21,9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
            에어비앤비에서 처리
          </button>
          <button
            onClick={handleDeclineClick}
            className="btn"
            style={{ 
              padding: "14px 20px",
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px"
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="20,6 9,17 4,12" />
            </svg>
            거절 완료
          </button>
        </div>
        {!item.action_url && (
          <div style={{ fontSize: "12px", color: "var(--text-muted)", textAlign: "center" }}>
            처리 링크가 없습니다
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Main Page Component
// ============================================================

export default function BookingRequestsPage() {
  // URL params
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSelectedId = searchParams.get("id");
  const urlThreadId = searchParams.get("thread"); // airbnb_thread_id

  // Mobile state
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);

  // Data
  const [allItems, setAllItems] = useState<PendingReservationDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { showToast } = useToast();

  // Filters
  const [tabFilter, setTabFilter] = useState<TabFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Selection - URL 파라미터가 있으면 우선 사용
  const [selectedId, setSelectedId] = useState<number | null>(
    urlSelectedId ? parseInt(urlSelectedId, 10) : null
  );
  const [highlightedId, setHighlightedId] = useState<number | null>(
    urlSelectedId ? parseInt(urlSelectedId, 10) : null
  );

  // URL 파라미터 변경 시 선택 업데이트 (id 또는 thread)
  useEffect(() => {
    if (allItems.length === 0) return;
    
    let targetItem: PendingReservationDTO | undefined;
    
    if (urlSelectedId) {
      const id = parseInt(urlSelectedId, 10);
      targetItem = allItems.find(item => item.id === id);
    } else if (urlThreadId) {
      targetItem = allItems.find(item => item.airbnb_thread_id === urlThreadId);
    }
    
    if (targetItem) {
      setSelectedId(targetItem.id);
      setHighlightedId(targetItem.id);
      // URL 파라미터 제거 (깔끔하게)
      setSearchParams({}, { replace: true });
      // 3초 후 하이라이트 제거
      const timer = setTimeout(() => setHighlightedId(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [urlSelectedId, urlThreadId, allItems, setSearchParams]);

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await getPendingReservations({ limit: 100, include_expired: true });
      // 남은 시간 기준 정렬 (긴급한 것 먼저)
      const sorted = [...res.items].sort((a, b) => {
        const hoursA = a.remaining_hours ?? 999;
        const hoursB = b.remaining_hours ?? 999;
        return hoursA - hoursB;
      });
      setAllItems(sorted);
      
      // URL 파라미터로 지정된 ID가 없고, 첫 로딩일 때만 첫 번째 항목 자동 선택
      if (sorted.length > 0 && !selectedId && !urlSelectedId) {
        setSelectedId(sorted[0].id);
      }
    } catch (e: any) {
      setError(e?.message || "데이터 로딩 실패");
    } finally {
      setLoading(false);
    }
  }, [urlSelectedId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 거절 처리 핸들러
  const handleDecline = async (id: number) => {
    try {
      await declinePendingReservation(id);
      
      // 목록에서 제거
      setAllItems(prev => prev.filter(item => item.id !== id));
      
      // 선택 해제 (다음 항목 선택)
      if (selectedId === id) {
        const remaining = allItems.filter(item => item.id !== id);
        setSelectedId(remaining.length > 0 ? remaining[0].id : null);
      }
      
      // 성공 토스트
      showToast({ type: "success", title: "거절 완료", message: "예약 요청이 거절되었습니다" });
    } catch (e: any) {
      showToast({ type: "error", title: "거절 실패", message: e?.message || "거절 처리 중 오류가 발생했습니다" });
    }
  };

  // Filtered items
  const filteredItems = allItems.filter(item => {
    // Tab filter
    if (tabFilter === "pending") {
      if ((item.remaining_hours ?? 0) <= 0) return false;
    } else if (tabFilter === "expired") {
      if ((item.remaining_hours ?? 0) > 0) return false;
    }

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchGuest = item.guest_name?.toLowerCase().includes(q);
      const matchProperty = item.property_code?.toLowerCase().includes(q);
      const matchListing = item.listing_name?.toLowerCase().includes(q);
      if (!matchGuest && !matchProperty && !matchListing) return false;
    }

    return true;
  });

  // Selected item
  const selectedItem = allItems.find(item => item.id === selectedId) || null;

  // Stats
  const pendingCount = allItems.filter(r => (r.remaining_hours ?? 0) > 0).length;
  const expiredCount = allItems.filter(r => (r.remaining_hours ?? 0) <= 0).length;
  const urgentCount = allItems.filter(r => {
    const h = r.remaining_hours ?? 0;
    return h > 0 && h <= 6;
  }).length;

  return (
    <div className={`booking-requests-page ${mobileDetailOpen ? "detail-open" : ""}`} style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Page Header */}
      <div className="page-header booking-requests-header">
        <div className="page-header-content">
          <div>
            <h1 className="page-title">예약 요청</h1>
            <p className="page-subtitle">
              대기 중인 예약 요청을 확인하고 에어비앤비에서 처리하세요
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {urgentCount > 0 && (
              <span className="badge badge-danger urgent-badge" style={{ padding: "6px 12px" }}>
                🚨 {urgentCount}
              </span>
            )}
            <button onClick={fetchData} disabled={loading} className="btn btn-secondary">
              {loading ? "⟳" : "새로고침"}
            </button>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: "var(--danger-bg)",
          border: "1px solid var(--danger)",
          borderRadius: "var(--radius)",
          padding: "12px 16px",
          margin: "0 32px 16px",
          color: "var(--danger)",
        }}>
          {error}
        </div>
      )}

      {/* Tabs + Filters */}
      <div className="booking-requests-filters" style={{ padding: "0 32px 16px", display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
        <div className="tabs">
          <button 
            onClick={() => setTabFilter("all")} 
            className={`tab ${tabFilter === "all" ? "active" : ""}`}
          >
            전체
            <span className="badge badge-default" style={{ marginLeft: "6px" }}>{allItems.length}</span>
          </button>
          <button 
            onClick={() => setTabFilter("pending")} 
            className={`tab ${tabFilter === "pending" ? "active" : ""}`}
          >
            대기중
            <span className="badge badge-warning" style={{ marginLeft: "6px" }}>{pendingCount}</span>
          </button>
          <button 
            onClick={() => setTabFilter("expired")} 
            className={`tab ${tabFilter === "expired" ? "active" : ""}`}
          >
            만료됨
            <span className="badge badge-default" style={{ marginLeft: "6px" }}>{expiredCount}</span>
          </button>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="게스트명, 숙소코드 검색..."
            className="input"
            style={{ width: "200px" }}
          />
        </div>
      </div>

      {/* Main Content - Inbox Layout */}
      <div className="inbox-layout">
        {/* List */}
        <div className="inbox-list card">
          <div className="card-header">
            <span className="card-title">예약 요청 목록</span>
            <span className="badge badge-default">{filteredItems.length}</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {loading ? (
              <SkeletonConversationList count={5} />
            ) : filteredItems.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">✓</div>
                <div className="empty-state-title">예약 요청이 없습니다</div>
                <div className="empty-state-text">필터를 변경하거나 새로고침하세요</div>
              </div>
            ) : (
              filteredItems.map(item => {
                const statusInfo = getStatusInfo(item.remaining_hours);
                const isExpired = (item.remaining_hours ?? 0) <= 0;
                const isHighlighted = item.id === highlightedId;
                
                return (
                  <div
                    key={item.id}
                    onClick={() => {
                      setSelectedId(item.id);
                      setMobileDetailOpen(true);
                    }}
                    className={`conversation-item ${item.id === selectedId ? "selected" : ""}`}
                    style={{
                      background: isExpired 
                        ? "var(--danger-bg)" 
                        : (item.remaining_hours ?? 999) <= 6 
                          ? "var(--warning-bg)" 
                          : undefined,
                      boxShadow: isHighlighted ? "0 0 0 2px var(--primary), var(--shadow-md)" : undefined,
                      transition: "box-shadow 0.3s ease",
                    }}
                  >
                    <div className="conversation-avatar">
                      {item.guest_name?.charAt(0) || "?"}
                    </div>
                    <div className="conversation-content">
                      <div className="conversation-name">
                        {item.guest_name || "게스트"}
                        {item.property_code && (
                          <span className="badge badge-primary" style={{ marginLeft: "8px", padding: "2px 8px", fontSize: "10px" }}>
                            {item.property_code}
                          </span>
                        )}
                      </div>
                      <div className="conversation-preview">
                        {formatDate(item.checkin_date)} → {formatDate(item.checkout_date)}
                        {item.nights && ` (${item.nights}박)`}
                      </div>
                      <div className="conversation-meta">
                        <span className={`badge ${statusInfo.className}`}>
                          {isExpired ? "만료" : statusInfo.label}
                        </span>
                        {item.expected_payout && (
                          <span style={{ color: "#16a34a", fontWeight: "600", fontSize: "12px" }}>
                            {formatCurrency(item.expected_payout)}
                          </span>
                        )}
                        <span className="conversation-time">{formatTime(item.received_at)}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Detail */}
        <div className="inbox-detail card">
          {/* Mobile Back Button */}
          <button 
            className="mobile-detail-back-btn"
            onClick={() => setMobileDetailOpen(false)}
            aria-label="목록으로 돌아가기"
          >
            ←
          </button>
          <DetailPanel 
            item={selectedItem} 
            loading={loading && !selectedItem} 
            onDecline={handleDecline}
          />
        </div>
      </div>
    </div>
  );
}
