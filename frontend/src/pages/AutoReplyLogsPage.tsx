// src/pages/AutoReplyLogsPage.tsx
import React from "react";
import { apiGet } from "../api/client";
import type { AutoReplyLogDTO } from "../types/intents";
import { LoadingOverlay } from "../components/ui/LoadingOverlay";
import { IntentBadge } from "../layout/IntentBadge";
import {
  runGmailAirbnbAutoReplyJob,
  type GmailAirbnbAutoReplyJobResponse,
} from "../api/jobs";

function formatDateTime(iso: string) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSendMode(mode: string) {
  switch (mode) {
    case "AUTOPILOT":
      return "AUTOPILOT";
    case "HITL":
      return "HITL(사람 검수)";
    default:
      return mode;
  }
}

const badgeBase =
  "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium";

function SentBadge({ sent }: { sent: boolean }) {
  if (sent) {
    return (
      <span
        className={`${badgeBase} border-emerald-500/50 bg-emerald-500/10 text-emerald-300`}
      >
        전송 완료
      </span>
    );
  }
  return (
    <span
      className={`${badgeBase} border-amber-500/50 bg-amber-500/10 text-amber-300`}
    >
      미전송
    </span>
  );
}

const AutoReplyLogsPage: React.FC = () => {
  const [logs, setLogs] = React.useState<AutoReplyLogDTO[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [jobRunning, setJobRunning] = React.useState(false);
  const [jobResult, setJobResult] =
    React.useState<GmailAirbnbAutoReplyJobResponse | null>(null);
  const [jobError, setJobError] = React.useState<string | null>(null);

  const loadLogs = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiGet<AutoReplyLogDTO[]>("/auto-replies", {
        limit: 50,
      });
      setLogs(data);
    } catch (err: any) {
      console.error(err);
      setError(
        err?.message ?? "Auto Reply 로그를 불러오는 중 오류가 발생했습니다.",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  const handleRunJob = async () => {
    const ok = window.confirm(
      "최근 1일 이내 Airbnb Gmail 메일에 대해 자동응답 파이프라인을 실행할까요?\n(이미 전송된 메시지는 스킵됩니다)",
    );
    if (!ok) return;

    setJobRunning(true);
    setJobError(null);
    setJobResult(null);

    try {
      const res = await runGmailAirbnbAutoReplyJob({
        max_results: 20,
        newer_than_days: 1,
        force: false,
      });
      setJobResult(res);
      // 실행 후 로그 새로고침
      void loadLogs();
    } catch (err: any) {
      console.error(err);
      setJobError(
        err?.message ??
          "Gmail Airbnb 자동응답 파이프라인 실행 중 오류가 발생했습니다.",
      );
    } finally {
      setJobRunning(false);
    }
  };

  return (
    <main className="flex-1 px-4 py-4 md:px-6 md:py-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-50 md:text-xl">
            Auto Reply 로그
          </h1>
          <p className="mt-1 text-xs text-slate-400 md:text-sm">
            LLM 기반 TONO 자동응답 내역과 Airbnb 자동응답 파이프라인 실행
            결과를 확인합니다.
          </p>
        </div>

        <div className="flex flex-col items-end gap-2 md:flex-row">
          <button
            type="button"
            onClick={handleRunJob}
            disabled={jobRunning}
            className="rounded-full border border-emerald-500/60 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-200 shadow-sm shadow-emerald-500/30 hover:bg-emerald-500/20 disabled:opacity-60"
          >
            {jobRunning
              ? "파이프라인 실행 중..."
              : "Gmail Airbnb 자동응답 파이프라인 실행"}
          </button>
          <button
            type="button"
            onClick={() => void loadLogs()}
            className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
          >
            새로고침
          </button>
        </div>
      </div>

      {jobError && (
        <div className="mb-3 rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-[11px] text-red-100 md:text-xs">
          {jobError}
        </div>
      )}

      {jobResult && (
        <div className="mb-3 rounded-xl border border-emerald-500/40 bg-emerald-500/5 px-3 py-2 text-[11px] text-emerald-100 md:text-xs">
          <div className="font-semibold">파이프라인 실행 결과 요약</div>
          <div className="mt-1 space-y-0.5">
            <div>
              Gmail 파싱: {jobResult.total_parsed}건 / 신규 저장:{" "}
              {jobResult.total_ingested}건
            </div>
            <div>
              자동응답 시도: {jobResult.total_target_messages}건 / 실제 발송:{" "}
              {jobResult.total_sent}건
            </div>
            <div>
              이미 발송되어 스킵: {jobResult.total_skipped_already_sent}건 / 본문
              없음 스킵: {jobResult.total_skipped_no_message}건
            </div>
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 shadow-xl shadow-black/30 md:p-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-xs text-slate-400 md:text-sm">
            최근 자동응답{" "}
            <span className="font-semibold text-slate-100">
              {logs.length}
            </span>
            건
          </div>
        </div>

        {isLoading && (
          <div className="relative">
            <LoadingOverlay message="자동응답 로그를 불러오는 중입니다..." />
          </div>
        )}

        {error && !isLoading && (
          <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200 md:text-sm">
            {error}
          </div>
        )}

        {!isLoading && !error && logs.length === 0 && (
          <div className="py-10 text-center text-xs text-slate-500 md:text-sm">
            아직 기록된 Auto Reply 로그가 없습니다.
          </div>
        )}

        {!isLoading && !error && logs.length > 0 && (
          <div className="mt-2 space-y-3 md:space-y-4">
            {logs.map((log) => {
              const failureReason = (log as any).failure_reason as
                | string
                | null
                | undefined;

              return (
                <article
                  key={log.id}
                  className="rounded-xl border border-slate-800/80 bg-slate-900/80 px-3 py-3 text-xs text-slate-100 shadow-sm shadow-black/40 md:px-4 md:py-4 md:text-sm"
                >
                  {/* 상단 메타 라인 */}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-slate-800/80 px-2 py-0.5 text-[11px] tracking-wide text-slate-200">
                        {log.property_code ?? "N/A"}
                      </span>
                      {log.ota && (
                        <span className="rounded-full bg-slate-800/80 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
                          {log.ota}
                        </span>
                      )}
                      <IntentBadge
                        intent={log.intent}
                        fineIntent={log.fine_intent}
                      />
                    </div>

                    <div className="flex items-center gap-2">
                      <SentBadge sent={log.sent} />
                      <span className="text-[11px] text-slate-400">
                        {formatDateTime(log.created_at)}
                      </span>
                    </div>
                  </div>

                  {/* 본문 */}
                  <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)] md:gap-4">
                    {/* 게스트 메시지 / 메타 */}
                    <div className="space-y-2">
                      {log.subject && (
                        <div className="truncate text-[11px] font-medium text-slate-100 md:text-sm">
                          {log.subject}
                        </div>
                      )}

                      {log.pure_guest_message && (
                        <div className="rounded-lg bg-slate-950/60 p-2 text-[11px] leading-relaxed text-slate-200 md:text-[13px]">
                          <div className="mb-1 text-[10px] font-semibold text-slate-400">
                            게스트 메시지
                          </div>
                          <p className="line-clamp-4 whitespace-pre-line">
                            {log.pure_guest_message}
                          </p>
                        </div>
                      )}

                      <div className="flex flex-wrap gap-1 text-[11px] text-slate-400">
                        <span>mode: {log.generation_mode}</span>
                        {log.template_id && (
                          <span className="before:mx-1 before:text-slate-600 before:content-['•']">
                            template: #{log.template_id}
                          </span>
                        )}
                        <span className="before:mx-1 before:text-slate-600 before:content-['•']">
                          send mode: {formatSendMode(log.send_mode)}
                        </span>
                        <span className="before:mx-1 before:text-slate-600 before:content-['•']">
                          confidence:{" "}
                          {log.intent_confidence != null
                            ? log.intent_confidence.toFixed(2)
                            : "-"}
                        </span>
                      </div>
                    </div>

                    {/* TONO 응답 내용 */}
                    <div className="space-y-2">
                      <div className="rounded-lg bg-emerald-900/10 p-2 ring-1 ring-emerald-500/20">
                        <div className="mb-1 flex items-center justify-between text-[10px] font-semibold text-emerald-200">
                          <span>TONO 자동응답</span>
                          <span className="text-[10px] text-emerald-300/80">
                            message_id: {log.message_id}
                          </span>
                        </div>
                        <p className="text-[11px] leading-relaxed text-slate-50 md:text-[13px] whitespace-pre-line">
                          {log.reply_text}
                        </p>
                      </div>

                      {failureReason && (
                        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-100 md:text-[12px]">
                          <div className="mb-1 text-[10px] font-semibold">
                            전송 실패 사유
                          </div>
                          <p className="whitespace-pre-line">{failureReason}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
};

export default AutoReplyLogsPage;
