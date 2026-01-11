// src/pages/ReservationsPage.tsx
/**
 * 예약 관리 페이지
 * 
 * - 예약 목록 조회 (필터, 검색, 페이지네이션)
 * - 객실 배정/변경
 * - Inbox 연동 (대화로 이동)
 */
import React, { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getReservationsPaginated } from "../api/reservations";
import { getPropertyGroups, getProperties } from "../api/properties";
import { RoomAssignmentModal } from "../components/conversations/RoomAssignmentModal";
import { useToast } from "../components/ui/Toast";
import type { Reservation, ReservationStatus, ReservationListParams } from "../types/reservations";
import type { PropertyGroupListItem, PropertyProfile } from "../types/properties";
import "../styles/inbox.css";

// 상태 라벨 맵
const STATUS_LABELS: Record<ReservationStatus, string> = {
  inquiry: "문의",
  awaiting_approval: "승인대기",
  declined: "거절",
  expired: "만료",
  confirmed: "확정",
  canceled: "취소",
  alteration_requested: "변경요청",
  pending: "대기",
};

const STATUS_COLORS: Record<ReservationStatus, string> = {
  inquiry: "review",
  awaiting_approval: "review",
  declined: "blocked",
  expired: "blocked",
  confirmed: "ready",
  canceled: "blocked",
  alteration_requested: "review",
  pending: "review",
};

// 날짜 포맷
function formatDate(dateStr?: string | null) {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleDateString("ko-KR", {
    month: "short",
    day: "numeric",
  });
}

function formatDateRange(checkin?: string | null, checkout?: string | null) {
  if (!checkin || !checkout) return "-";
  return `${formatDate(checkin)} ~ ${formatDate(checkout)}`;
}

// 오늘 날짜 (YYYY-MM-DD)
function getToday() {
  return new Date().toISOString().split("T")[0];
}

// 30일 후
function getDaysLater(days: number) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().split("T")[0];
}

export default function ReservationsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showToast } = useToast();

  // 데이터
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 필터 옵션
  const [groups, setGroups] = useState<PropertyGroupListItem[]>([]);
  const [properties, setProperties] = useState<PropertyProfile[]>([]);

  // 필터 상태
  const [filters, setFilters] = useState<ReservationListParams>({
    status: (searchParams.get("status") as ReservationStatus) || undefined,
    group_code: searchParams.get("group_code") || undefined,
    property_code: searchParams.get("property_code") || undefined,
    unassigned_only: searchParams.get("unassigned_only") === "true",
    checkin_from: searchParams.get("checkin_from") || getToday(),
    checkin_to: searchParams.get("checkin_to") || getDaysLater(90),
    search: searchParams.get("search") || undefined,
    limit: 50,
    offset: 0,
  });

  // 검색 입력 (debounce용)
  const [searchInput, setSearchInput] = useState(filters.search || "");

  // 모달
  const [selectedReservation, setSelectedReservation] = useState<Reservation | null>(null);
  const [showRoomModal, setShowRoomModal] = useState(false);

  // 필터 옵션 로드
  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [groupsData, propertiesData] = await Promise.all([
          getPropertyGroups({ is_active: true }),
          getProperties({ is_active: true }),
        ]);
        setGroups(groupsData);
        setProperties(propertiesData);
      } catch (e) {
        console.error("Failed to load filter options:", e);
      }
    };
    loadOptions();
  }, []);

  // 예약 목록 로드
  const loadReservations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getReservationsPaginated(filters);
      setReservations(res.items);
      setTotal(res.total);
    } catch (e: any) {
      setError(e.message || "예약 목록을 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadReservations();
  }, [loadReservations]);

  // URL 파라미터 동기화
  useEffect(() => {
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    if (filters.group_code) params.set("group_code", filters.group_code);
    if (filters.property_code) params.set("property_code", filters.property_code);
    if (filters.unassigned_only) params.set("unassigned_only", "true");
    if (filters.checkin_from) params.set("checkin_from", filters.checkin_from);
    if (filters.checkin_to) params.set("checkin_to", filters.checkin_to);
    if (filters.search) params.set("search", filters.search);
    setSearchParams(params, { replace: true });
  }, [filters, setSearchParams]);

  // 검색 debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== (filters.search || "")) {
        setFilters((prev) => ({
          ...prev,
          search: searchInput || undefined,
          offset: 0,
        }));
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // 필터 변경 핸들러
  const updateFilter = (key: keyof ReservationListParams, value: any) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
      offset: 0, // 필터 변경 시 페이지 리셋
    }));
  };

  // 페이지 변경
  const goToPage = (page: number) => {
    setFilters((prev) => ({
      ...prev,
      offset: page * (prev.limit || 50),
    }));
  };

  const currentPage = Math.floor((filters.offset || 0) / (filters.limit || 50));
  const totalPages = Math.ceil(total / (filters.limit || 50));

  // Inbox로 이동
  const goToInbox = (reservation: Reservation) => {
    navigate(`/inbox?thread=${reservation.airbnb_thread_id}`);
  };

  // 객실 배정 모달 열기
  const openRoomAssignment = (reservation: Reservation) => {
    setSelectedReservation(reservation);
    setShowRoomModal(true);
  };

  // 배정 완료 핸들러
  const handleAssigned = () => {
    loadReservations();
    showToast({ type: "success", title: "객실이 배정되었습니다." });
  };

  // 필터 초기화
  const resetFilters = () => {
    setFilters({
      checkin_from: getToday(),
      checkin_to: getDaysLater(90),
      limit: 50,
      offset: 0,
    });
    setSearchInput("");
  };

  return (
    <div className="inbox-page reservations-page">
      {/* Header */}
      <div className="inbox-top-header">
        <div className="inbox-top-header-left">
          <h1 className="inbox-page-title">예약 관리</h1>
          <span
            className="inbox-list-title-badge"
            style={{ fontSize: "12px" }}
          >
            {total}건
          </span>
        </div>
        <div className="inbox-top-header-right">
          <button
            className="inbox-btn inbox-btn-secondary inbox-btn-sm"
            onClick={resetFilters}
          >
            필터 초기화
          </button>
          <button
            className="inbox-btn inbox-btn-primary inbox-btn-sm"
            onClick={loadReservations}
            disabled={loading}
          >
            {loading ? "로딩..." : "새로고침"}
          </button>
        </div>
      </div>

      {/* Filter Row */}
      <div className="inbox-filter-row" style={{ gap: "12px" }}>
        {/* 검색 */}
        <div className="inbox-search" style={{ marginBottom: 0, width: "200px" }}>
          <span className="inbox-search-icon">🔍</span>
          <input
            type="text"
            className="inbox-search-input"
            placeholder="게스트명, 예약코드"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        {/* 상태 필터 */}
        <select
          className="inbox-filter-select"
          value={filters.status || ""}
          onChange={(e) => updateFilter("status", e.target.value || undefined)}
        >
          <option value="">모든 상태</option>
          <option value="confirmed">확정</option>
          <option value="inquiry">문의</option>
          <option value="awaiting_approval">승인대기</option>
          <option value="canceled">취소</option>
          <option value="declined">거절</option>
          <option value="expired">만료</option>
        </select>

        {/* 그룹 필터 */}
        <select
          className="inbox-filter-select"
          value={filters.group_code || ""}
          onChange={(e) => updateFilter("group_code", e.target.value || undefined)}
        >
          <option value="">모든 그룹</option>
          {groups.map((g) => (
            <option key={g.group_code} value={g.group_code}>
              {g.name}
            </option>
          ))}
        </select>

        {/* 숙소 필터 */}
        <select
          className="inbox-filter-select"
          value={filters.property_code || ""}
          onChange={(e) => updateFilter("property_code", e.target.value || undefined)}
        >
          <option value="">모든 숙소</option>
          {properties.map((p) => (
            <option key={p.property_code} value={p.property_code}>
              {p.name}
            </option>
          ))}
        </select>

        {/* 미배정만 */}
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "13px",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={filters.unassigned_only || false}
            onChange={(e) => updateFilter("unassigned_only", e.target.checked)}
          />
          미배정만
        </label>

        {/* 날짜 필터 */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginLeft: "auto" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>체크인:</span>
          <input
            type="date"
            className="inbox-filter-select"
            value={filters.checkin_from || ""}
            onChange={(e) => updateFilter("checkin_from", e.target.value || undefined)}
          />
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>~</span>
          <input
            type="date"
            className="inbox-filter-select"
            value={filters.checkin_to || ""}
            onChange={(e) => updateFilter("checkin_to", e.target.value || undefined)}
          />
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        {error ? (
          <div
            style={{
              background: "var(--danger-bg)",
              border: "1px solid var(--danger)",
              borderRadius: "var(--radius)",
              padding: "16px",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        ) : loading && reservations.length === 0 ? (
          <div className="inbox-empty-state">
            <div className="loading-spinner" />
          </div>
        ) : reservations.length === 0 ? (
          <div className="inbox-empty-state">
            <div className="inbox-empty-state-icon">📋</div>
            <div className="inbox-empty-state-title">예약이 없습니다</div>
            <div className="inbox-empty-state-text">
              필터 조건을 변경해 보세요
            </div>
          </div>
        ) : (
          <>
            {/* Table */}
            <div
              style={{
                background: "var(--surface)",
                borderRadius: "var(--radius-lg)",
                border: "1px solid var(--border)",
                overflow: "hidden",
              }}
            >
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: "13px",
                }}
              >
                <thead>
                  <tr
                    style={{
                      background: "var(--bg)",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <th style={{ padding: "12px 16px", textAlign: "left", fontWeight: 600, width: "120px" }}>
                      게스트
                    </th>
                    <th style={{ padding: "12px 16px", textAlign: "left", fontWeight: 600, width: "100px" }}>
                      예약코드
                    </th>
                    <th style={{ padding: "12px 16px", textAlign: "left", fontWeight: 600, width: "140px", whiteSpace: "nowrap" }}>
                      일정
                    </th>
                    <th style={{ padding: "12px 16px", textAlign: "left", fontWeight: 600 }}>
                      숙소/그룹
                    </th>
                    <th style={{ padding: "12px 16px", textAlign: "center", fontWeight: 600, width: "80px" }}>
                      상태
                    </th>
                    <th style={{ padding: "12px 16px", textAlign: "center", fontWeight: 600, width: "90px" }}>
                      배정
                    </th>
                    <th style={{ padding: "12px 16px", textAlign: "center", fontWeight: 600, width: "80px" }}>
                      액션
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {reservations.map((r) => (
                    <tr
                      key={r.id}
                      style={{
                        borderBottom: "1px solid var(--border-light)",
                        transition: "background 0.15s",
                      }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.background = "var(--bg)")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.background = "transparent")
                      }
                    >
                      {/* 게스트 */}
                      <td style={{ padding: "14px 16px" }}>
                        <div style={{ fontWeight: 500 }}>{r.guest_name || "-"}</div>
                        {r.guest_count && (
                          <div
                            style={{
                              fontSize: "11px",
                              color: "var(--text-secondary)",
                              marginTop: "2px",
                            }}
                          >
                            👤 {r.guest_count}명
                            {(r.child_count ?? 0) > 0 && ` (아동 ${r.child_count})`}
                          </div>
                        )}
                      </td>

                      {/* 예약코드 */}
                      <td style={{ padding: "14px 16px" }}>
                        <code
                          style={{
                            fontSize: "11px",
                            background: "var(--bg)",
                            padding: "2px 6px",
                            borderRadius: "4px",
                          }}
                        >
                          {r.reservation_code || "-"}
                        </code>
                      </td>

                      {/* 일정 */}
                      <td style={{ padding: "14px 16px", whiteSpace: "nowrap" }}>
                        <div>{formatDateRange(r.checkin_date, r.checkout_date)}</div>
                      </td>

                      {/* 숙소/그룹 */}
                      <td style={{ padding: "14px 16px", maxWidth: "250px" }}>
                        {r.property_name ? (
                          <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.property_name}</div>
                        ) : r.group_name ? (
                          <div style={{ color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            📁 {r.group_name}
                          </div>
                        ) : (
                          <div style={{ color: "var(--text-muted)" }}>-</div>
                        )}
                        {r.listing_name && (
                          <div
                            style={{
                              fontSize: "11px",
                              color: "var(--text-muted)",
                              marginTop: "2px",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {r.listing_name}
                          </div>
                        )}
                      </td>

                      {/* 상태 */}
                      <td style={{ padding: "14px 16px", textAlign: "center", whiteSpace: "nowrap" }}>
                        <span
                          className={`inbox-status-badge ${
                            STATUS_COLORS[r.status as ReservationStatus] || ""
                          }`}
                        >
                          {STATUS_LABELS[r.status as ReservationStatus] || r.status}
                        </span>
                      </td>

                      {/* 배정 상태 */}
                      <td style={{ padding: "14px 16px", textAlign: "center", whiteSpace: "nowrap" }}>
                        {r.room_assigned ? (
                          <span
                            className="inbox-status-badge ready"
                            style={{ fontSize: "11px" }}
                          >
                            ✓ 배정완료
                          </span>
                        ) : r.effective_group_code ? (
                          <span
                            className="inbox-status-badge review"
                            style={{ fontSize: "11px" }}
                          >
                            미배정
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
                            -
                          </span>
                        )}
                      </td>

                      {/* 액션 */}
                      <td style={{ padding: "14px 16px", textAlign: "center" }}>
                        <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
                          <button
                            className="inbox-btn inbox-btn-ghost inbox-btn-sm"
                            onClick={() => goToInbox(r)}
                            title="Inbox에서 보기"
                          >
                            💬
                          </button>
                          {r.can_reassign && (
                            <button
                              className="inbox-btn inbox-btn-ghost inbox-btn-sm"
                              onClick={() => openRoomAssignment(r)}
                              title="객실 배정"
                            >
                              🛏️
                            </button>
                          )}
                          {r.airbnb_thread_id && (
                            <a
                              href={`https://www.airbnb.co.kr/hosting/thread/${r.airbnb_thread_id}?thread_type=home_booking`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inbox-btn inbox-btn-ghost inbox-btn-sm"
                              title="에어비앤비에서 보기"
                            >
                              🏠
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  marginTop: "20px",
                }}
              >
                <button
                  className="inbox-btn inbox-btn-secondary inbox-btn-sm"
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 0}
                >
                  ←
                </button>
                
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 5) {
                    pageNum = i;
                  } else if (currentPage < 3) {
                    pageNum = i;
                  } else if (currentPage > totalPages - 4) {
                    pageNum = totalPages - 5 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }
                  return (
                    <button
                      key={pageNum}
                      className={`inbox-btn inbox-btn-sm ${
                        pageNum === currentPage
                          ? "inbox-btn-primary"
                          : "inbox-btn-ghost"
                      }`}
                      onClick={() => goToPage(pageNum)}
                    >
                      {pageNum + 1}
                    </button>
                  );
                })}

                <button
                  className="inbox-btn inbox-btn-secondary inbox-btn-sm"
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={currentPage >= totalPages - 1}
                >
                  →
                </button>
                
                <span
                  style={{
                    marginLeft: "12px",
                    fontSize: "12px",
                    color: "var(--text-secondary)",
                  }}
                >
                  총 {total}건 중 {filters.offset! + 1}-
                  {Math.min(filters.offset! + filters.limit!, total)}
                </span>
              </div>
            )}
          </>
        )}
      </div>

      {/* Room Assignment Modal */}
      {showRoomModal && selectedReservation?.airbnb_thread_id && (
        <RoomAssignmentModal
          threadId={selectedReservation.airbnb_thread_id}
          onClose={() => {
            setShowRoomModal(false);
            setSelectedReservation(null);
          }}
          onAssigned={handleAssigned}
        />
      )}
    </div>
  );
}
