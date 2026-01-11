// src/components/conversations/RoomAssignmentModal.tsx
/**
 * 객실 배정/변경 모달
 * 
 * 그룹 소속 예약에서 특정 객실을 선택하여 배정
 */
import { useState, useEffect } from "react";
import { getRoomAssignmentInfo, assignRoom, unassignRoom } from "../../api/reservations";
import type { RoomAssignmentInfo, AvailableRoom } from "../../types/reservations";

interface RoomAssignmentModalProps {
  threadId: string;
  onClose: () => void;
  onAssigned: () => void;
}

export function RoomAssignmentModal({
  threadId,
  onClose,
  onAssigned,
}: RoomAssignmentModalProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<RoomAssignmentInfo | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null);

  // 데이터 로드
  useEffect(() => {
    loadInfo();
  }, [threadId]);

  const loadInfo = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRoomAssignmentInfo(threadId);
      setInfo(data);
      // 현재 배정된 객실 선택
      if (data.reservation.property_code) {
        setSelectedRoom(data.reservation.property_code);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAssign = async () => {
    if (!selectedRoom) return;

    setSaving(true);
    setError(null);
    try {
      await assignRoom(threadId, { property_code: selectedRoom });
      onAssigned();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleUnassign = async () => {
    if (!info?.reservation.property_code) return;

    setSaving(true);
    setError(null);
    try {
      await unassignRoom(threadId);
      onAssigned();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString("ko-KR", {
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div 
      className="modal-overlay" 
      onClick={onClose}
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
    >
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{ 
          maxWidth: "560px", 
          width: "90%",
          maxHeight: "80vh",
          background: "var(--surface)",
          borderRadius: "12px",
          boxShadow: "var(--shadow-lg)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Header */}
        <div 
          className="modal-header"
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <h2 className="modal-title" style={{ margin: 0, fontSize: "18px" }}>객실 배정</h2>
          <button 
            className="modal-close" 
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: "24px",
              cursor: "pointer",
              color: "var(--text-secondary)",
            }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div 
          className="modal-body"
          style={{
            padding: "16px 20px",
            overflowY: "auto",
            flex: 1,
          }}
        >
          {loading ? (
            <div className="empty-state">
              <div className="loading-spinner" />
            </div>
          ) : error ? (
            <div
              style={{
                background: "var(--danger-bg)",
                border: "1px solid var(--danger)",
                borderRadius: "var(--radius)",
                padding: "12px 16px",
                color: "var(--danger)",
              }}
            >
              {error}
            </div>
          ) : info ? (
            <>
              {/* 예약 정보 */}
              <div
                style={{
                  background: "var(--bg-secondary)",
                  borderRadius: "8px",
                  padding: "16px",
                  marginBottom: "16px",
                }}
              >
                <div style={{ fontWeight: "600", marginBottom: "8px" }}>
                  {info.reservation.guest_name || "게스트"} 님
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "16px",
                    fontSize: "14px",
                    color: "var(--text-secondary)",
                  }}
                >
                  <span>
                    📅 {formatDate(info.reservation.checkin_date)} ~{" "}
                    {formatDate(info.reservation.checkout_date)}
                  </span>
                  {info.reservation.guest_count && (
                    <span>👤 {info.reservation.guest_count}명</span>
                  )}
                </div>
                {info.group && (
                  <div
                    style={{
                      marginTop: "8px",
                      fontSize: "13px",
                      color: "var(--text-muted)",
                    }}
                  >
                    📁 그룹: {info.group.name}
                  </div>
                )}
              </div>

              {/* 객실 선택 */}
              {info.available_rooms.length > 0 ? (
                <div>
                  <div
                    style={{
                      fontSize: "14px",
                      fontWeight: "500",
                      marginBottom: "12px",
                    }}
                  >
                    객실 선택
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {info.available_rooms.map((room) => (
                      <RoomOption
                        key={room.property_code}
                        room={room}
                        selected={selectedRoom === room.property_code}
                        currentRoom={info.reservation.property_code}
                        onSelect={() => setSelectedRoom(room.property_code)}
                      />
                    ))}
                  </div>
                </div>
              ) : (
                <div className="empty-state" style={{ padding: "24px" }}>
                  <div style={{ fontSize: "14px", color: "var(--text-muted)" }}>
                    배정 가능한 객실이 없습니다.
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div 
          className="modal-footer"
          style={{
            padding: "16px 20px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            justifyContent: "flex-end",
            gap: "8px",
            flexShrink: 0,
          }}
        >
          {info?.reservation.property_code && info?.reservation.group_code && (
            <button
              className="btn btn-secondary"
              onClick={handleUnassign}
              disabled={saving}
              style={{ marginRight: "auto" }}
            >
              배정 해제
            </button>
          )}
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>
            취소
          </button>
          <button
            className="btn btn-primary"
            onClick={handleAssign}
            disabled={
              saving ||
              !selectedRoom ||
              selectedRoom === info?.reservation.property_code
            }
          >
            {saving ? "저장 중..." : "배정하기"}
          </button>
        </div>
      </div>
    </div>
  );
}

// 객실 옵션 컴포넌트
interface RoomOptionProps {
  room: AvailableRoom;
  selected: boolean;
  currentRoom?: string;
  onSelect: () => void;
}

function RoomOption({ room, selected, currentRoom, onSelect }: RoomOptionProps) {
  const isCurrent = room.property_code === currentRoom;

  return (
    <div
      onClick={room.is_available || isCurrent ? onSelect : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "12px",
        padding: "12px 16px",
        borderRadius: "8px",
        border: selected
          ? "2px solid var(--primary)"
          : "1px solid var(--border)",
        background: selected ? "var(--primary-bg)" : "var(--bg-primary)",
        cursor: room.is_available || isCurrent ? "pointer" : "not-allowed",
        opacity: room.is_available || isCurrent ? 1 : 0.6,
        transition: "all 0.15s ease",
      }}
    >
      {/* 라디오 버튼 */}
      <div
        style={{
          width: "20px",
          height: "20px",
          borderRadius: "50%",
          border: selected
            ? "6px solid var(--primary)"
            : "2px solid var(--border)",
          background: "var(--bg-primary)",
          flexShrink: 0,
        }}
      />

      {/* 객실 정보 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: "500", marginBottom: "2px" }}>
          {room.name}
          <span
            style={{
              marginLeft: "8px",
              fontSize: "12px",
              color: "var(--text-muted)",
            }}
          >
            {room.property_code}
          </span>
          {isCurrent && (
            <span
              className="badge badge-primary"
              style={{ marginLeft: "8px", fontSize: "10px" }}
            >
              현재 배정
            </span>
          )}
        </div>
        <div
          style={{
            fontSize: "13px",
            color: "var(--text-secondary)",
            display: "flex",
            gap: "12px",
          }}
        >
          {room.bed_types && <span>🛏️ {room.bed_types}</span>}
          {room.capacity_max && <span>👤 최대 {room.capacity_max}명</span>}
        </div>
      </div>

      {/* 상태 */}
      <div style={{ flexShrink: 0 }}>
        {room.is_available ? (
          <span
            className="badge"
            style={{
              background: "#dcfce7",
              color: "#166534",
            }}
          >
            가능
          </span>
        ) : (
          <div style={{ textAlign: "right" }}>
            <span
              className="badge"
              style={{
                background: "var(--danger-bg)",
                color: "var(--danger)",
              }}
            >
              예약 있음
            </span>
            {room.conflict_info && (
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  marginTop: "4px",
                }}
              >
                {room.conflict_info}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
