// src/pages/StaffNotificationsPage.tsx
import React from "react";
import type { StaffNotificationDTO } from "../types/intents";
import {
  fetchStaffNotifications,
  updateStaffNotificationStatus,
  type StaffNotificationFilters,
} from "../api/staffNotifications";
import { LoadingOverlay } from "../components/ui/LoadingOverlay";

export const StaffNotificationsPage: React.FC = () => {
  const [items, setItems] = React.useState<StaffNotificationDTO[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [onlyOpen, setOnlyOpen] = React.useState(true);
  const [updatingId, setUpdatingId] = React.useState<number | null>(null);

  const loadNotifications = React.useCallback(
    async (filters: StaffNotificationFilters = {}) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchStaffNotifications({
          unresolved_only: onlyOpen,
          limit: 100,
          ...filters,
        });
        setItems(data);
      } catch (err: any) {
        console.error(err);
        setError(
          err?.message ??
            "스태프 알림을 불러오는 중 오류가 발생했습니다.",
        );
      } finally {
        setLoading(false);
      }
    },
    [onlyOpen],
  );

  React.useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  const handleToggleOpenFilter = () => {
    setOnlyOpen((prev) => !prev);
  };

  // ✅ 처리 완료 클릭 핸들러
  const handleResolve = async (id: number) => {
    const target = items.find((n) => n.id === id);
    if (!target) return;

    const ok = window.confirm("이 알림을 처리 완료로 표시할까요?");
    if (!ok) return;

    setUpdatingId(id);

    try {
      // status: "RESOLVED" 로 PATCH
      const updated = await updateStaffNotificationStatus(id, "RESOLVED");

      // 로컬 상태 반영 + unresolved_only=true면 RESOLVED 제거
      setItems((prev) =>
        prev
          .map((n) => (n.id === id ? updated : n))
          .filter((n) => !onlyOpen || n.status !== "RESOLVED"),
      );
    } catch (err: any) {
      console.error(err);
      alert(
        err?.message ??
          "알림을 처리 완료로 변경하는 중 오류가 발생했습니다.",
      );
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="relative flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-base font-semibold text-slate-50 md:text-lg">
            알림센터 (Staff Notifications)
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            TONO가 생성한 후속 작업 알림을 모아서 관리합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleToggleOpenFilter}
            className={[
              "inline-flex items-center rounded-full border px-3 py-1.5 text-xs",
              onlyOpen
                ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                : "border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800",
            ].join(" ")}
          >
            {onlyOpen ? "미처리만 보기 (ON)" : "미처리만 보기 (OFF)"}
          </button>
          <button
            type="button"
            onClick={() => void loadNotifications()}
            className="inline-flex items-center rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
          >
            새로고침
          </button>
        </div>
      </div>

      <div className="relative flex-1 overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-4">
        {loading && items.length === 0 && (
          <LoadingOverlay message="스태프 알림을 불러오는 중입니다..." />
        )}

        {error ? (
          <div className="text-xs text-red-400">{error}</div>
        ) : items.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            표시할 스태프 알림이 없습니다.
          </div>
        ) : (
          <div className="h-full space-y-3 overflow-y-auto pr-1">
            {items.map((n) => {
              const status =
                (n.status || "").toUpperCase() as
                  | "OPEN"
                  | "IN_PROGRESS"
                  | "RESOLVED"
                  | string;

              const statusClass =
                status === "RESOLVED"
                  ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/40"
                  : status === "IN_PROGRESS"
                  ? "bg-amber-500/10 text-amber-200 border-amber-500/40"
                  : "bg-red-500/10 text-red-200 border-red-500/40";

              const isResolving = updatingId === n.id;

              return (
                <div
                  key={n.id}
                  className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 hover:border-slate-600"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-col gap-1">
                      {/* 상단 메타 정보 */}
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                        <span className="font-mono text-[11px] text-slate-300">
                          {n.property_code || "N/A"}
                        </span>
                        <span className="text-slate-600">·</span>
                        <span>{n.ota || "unknown"}</span>
                        <span className="text-slate-600">·</span>
                        <span>{n.guest_name || "(게스트 이름 없음)"}</span>
                        {n.checkin_date && (
                          <>
                            <span className="text-slate-600">·</span>
                            <span>체크인 {n.checkin_date}</span>
                          </>
                        )}
                      </div>

                      <div className="mt-1 text-sm text-slate-100">
                        {n.message_summary}
                      </div>

                      {n.follow_up_actions.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {n.follow_up_actions.map((action, idx) => (
                            <span
                              key={idx}
                              className="inline-flex items-center rounded-full border border-blue-500/40 bg-blue-500/10 px-2 py-0.5 text-[11px] text-blue-200"
                            >
                              {action}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* status + 처리 완료 버튼 */}
                    <div className="flex flex-col items-end gap-2">
                      <span
                        className={[
                          "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px]",
                          statusClass,
                        ].join(" ")}
                      >
                        {n.status}
                      </span>

                      {status !== "RESOLVED" && (
                        <button
                          type="button"
                          onClick={() => void handleResolve(n.id)}
                          disabled={isResolving}
                          className="inline-flex items-center rounded-full border border-emerald-500/60 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-60"
                        >
                          {isResolving ? "처리 중..." : "처리 완료"}
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                    <span>message_id: {n.message_id}</span>
                    <span>
                      생성:{" "}
                      {new Date(n.created_at).toLocaleString("ko-KR")}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
