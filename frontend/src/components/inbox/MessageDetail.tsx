// src/components/inbox/MessageDetail.tsx
import React from "react";
import type { MessageDetailDTO } from "../../types/messages";
import type { AutoReplyLogDTO } from "../../types/intents";
import {
  requestMessageAutoReplySuggestion,
  sendMessageAutoReply,
} from "../../api/messages";
import { AutoReplyStatus } from "./AutoReplyStatus";
import { IntentBadge } from "../../layout/IntentBadge";

interface MessageDetailProps {
  detail: MessageDetailDTO | null;
  loading?: boolean;
  autoReply?: AutoReplyLogDTO | null;
  // 🔥 InboxPage에서 넘겨주는 프리뷰 자동응답 텍스트
  previewReply?: string | null;
}

export const MessageDetail: React.FC<MessageDetailProps> = ({
  detail,
  loading,
  autoReply,
  previewReply,
}) => {
  
  const [draft, setDraft] = React.useState("");
  const [suggestLoading, setSuggestLoading] = React.useState(false);
  const [sendLoading, setSendLoading] = React.useState(false);
  const [suggestError, setSuggestError] = React.useState<string | null>(null);
  const [sendResult, setSendResult] = React.useState<
    { sent: boolean; skipReason: string | null } | null
  >(null);

  // 🔥 previewReply / autoReply 변화에 따라 draft 초기값 세팅
  React.useEffect(() => {
    
    setSuggestError(null);
    setSendResult(null);

    if (previewReply && previewReply.trim().length > 0) {
      // 1순위: Gmail 프리뷰 파이프라인에서 생성된 자동응답
      setDraft(previewReply.trim());
    } else if (autoReply?.reply_text && autoReply.reply_text.trim().length > 0) {
      // 2순위: 기존 AutoReply 로그
      setDraft(autoReply.reply_text);
    } else {
      // 없으면 비우기
      setDraft("");
    }
  }, [detail?.id, previewReply, autoReply?.reply_text]);

  if (!detail && !loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        좌측에서 메시지를 선택하면 상세 내용이 여기에 표시됩니다.
      </div>
    );
  }

  const msg = detail;

  const nights =
    msg?.checkin_date && msg?.checkout_date
      ? (() => {
          const inDate = new Date(msg.checkin_date);
          const outDate = new Date(msg.checkout_date);
          const diff = outDate.getTime() - inDate.getTime();
          const days = Math.round(diff / (1000 * 60 * 60 * 24));
          return days > 0 ? days : null;
        })()
      : null;

  const handleSuggest = async () => {
    if (!msg) return;
    setSuggestLoading(true);
    setSuggestError(null);
    setSendResult(null);
    try {
      const res = await requestMessageAutoReplySuggestion(msg.id, {
        ota: msg.ota ?? undefined,
        property_code: msg.property_code ?? undefined,
        locale: "ko",
        use_llm: true,
      });
      setDraft(res.reply_text);
    } catch (err: any) {
      console.error(err);
      setSuggestError(
        err?.message ?? "자동응답 제안을 가져오는 중 오류가 발생했습니다.",
      );
    } finally {
      setSuggestLoading(false);
    }
  };

  const handleSend = async () => {
    if (!msg || !draft.trim()) return;
    setSendLoading(true);
    setSendResult(null);
    try {
      const res = await sendMessageAutoReply(msg.id, {
        final_reply_text: draft.trim(),
        force: true,
      });
      setSendResult({
        sent: res.sent,
        skipReason: res.skip_reason,
      });

      if (res.sent) {
        alert("자동응답이 발송되었습니다.");
      } else {
        alert(
          `자동응답이 발송되지 않았습니다: ${
            res.skip_reason ?? "알 수 없는 이유"
          }`,
        );
      }
    } catch (err: any) {
      console.error(err);
      alert(
        err?.message ?? "자동응답을 발송하는 중 오류가 발생했습니다.",
      );
    } finally {
      setSendLoading(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4 md:p-5">
      {!msg ? (
        <div className="text-xs text-slate-400">로딩 중...</div>
      ) : (
        <>
          {/* 상단 메타 */}
          <section className="rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex flex-col gap-1">
                <div className="text-xs text-slate-400">
                  {msg.property_code || "N/A"} · {msg.ota || "unknown"} · 메시지 #
                  {msg.id}
                </div>
                <div className="text-sm font-semibold text-slate-50">
                  {msg.subject || "(제목 없음)"}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                  {msg.guest_name && <span>게스트: {msg.guest_name}</span>}
                  {msg.checkin_date && (
                    <>
                      <span className="text-slate-600">·</span>
                      <span>
                        체크인 {msg.checkin_date}
                        {msg.checkout_date ? ` ~ ${msg.checkout_date}` : ""}
                        {nights ? ` (${nights}박)` : ""}
                      </span>
                    </>
                  )}
                  <span className="text-slate-600">·</span>
                  <span>
                    수신: {new Date(msg.received_at).toLocaleString("ko-KR")}
                  </span>
                </div>
              </div>

              <div className="flex flex-col items-end gap-1 text-[11px] text-slate-400">
                <span>from: {msg.from_email || "(알 수 없음)"}</span>
                <span>
                  actor: {msg.sender_actor} / {msg.actionability}
                </span>
              </div>
            </div>
          </section>

          {/* 게스트 메시지 */}
          <section className="space-y-2 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-xs font-semibold text-slate-300">
                게스트 메시지
              </h2>
            </div>
            <div className="whitespace-pre-wrap rounded-lg bg-slate-950 px-3 py-2 text-sm text-slate-100">
              {msg.pure_guest_message || msg.text_body || "(본문 없음)"}
            </div>
          </section>

          {/* Intent & 라벨 */}
          <section className="space-y-2 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-xs font-semibold text-slate-300">
                Intent & 라벨 히스토리
              </h2>
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                <IntentBadge intent={msg.intent} fineIntent={msg.fine_intent} />
                <span>
                  신뢰도:{" "}
                  {msg.intent_confidence != null
                    ? msg.intent_confidence.toFixed(2)
                    : "-"}
                </span>
                {msg.fine_intent_confidence != null && (
                  <span>
                    세부 Intent: {msg.fine_intent_confidence.toFixed(2)}
                  </span>
                )}
                {msg.suggested_action && (
                  <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                    {msg.suggested_action}
                  </span>
                )}
                {msg.allow_auto_send === false && (
                  <span className="rounded-full border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-[10px] text-red-200">
                    AUTO SEND 비권장
                  </span>
                )}
              </div>
            </div>

            {msg.fine_intent_reasons && (
              <div className="rounded-lg bg-slate-950 px-3 py-2 text-[11px] text-slate-200">
                <div className="mb-1 text-[10px] font-semibold text-slate-400">
                  세부 Intent 판단 근거
                </div>
                <p className="whitespace-pre-line">{msg.fine_intent_reasons}</p>
              </div>
            )}

            {msg.labels.length > 0 ? (
              <div className="space-y-1">
                <div className="text-[11px] font-medium text-slate-500">
                  라벨 히스토리
                </div>
                <ul className="space-y-1 text-[11px] text-slate-400">
                  {msg.labels.map((label) => (
                    <li key={label.id} className="flex items-center gap-2">
                      <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300">
                        {label.source}
                      </span>
                      <span>{label.intent}</span>
                      <span className="text-slate-500">
                        {new Date(label.created_at).toLocaleString("ko-KR")}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="text-[11px] text-slate-500">
                이 메시지에 저장된 라벨이 없습니다.
              </div>
            )}
          </section>

          {/* TONO 자동응답 */}
          <section className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold text-slate-300">
                TONO 자동응답
              </h2>
              {autoReply && (
                <AutoReplyStatus
                  sent={!!autoReply.sent}
                  sendMode={autoReply.send_mode}
                />
              )}
            </div>

            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-[11px] text-slate-400">
                  게스트 메시지에 대한 자동응답을 제안받고, 수정 후 발송할 수
                  있습니다.
                  {previewReply && (
                    <span className="ml-1 text-emerald-300">
                      (Gmail 프리뷰 결과가 아래에 미리 채워져 있습니다)
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={handleSuggest}
                    disabled={suggestLoading || !msg}
                    className="rounded-full border border-sky-500/60 bg-sky-500/10 px-3 py-1 text-[11px] text-sky-200 hover:bg-sky-500/20 disabled:opacity-60"
                  >
                    {suggestLoading ? "제안 생성 중..." : "자동응답 제안 받기"}
                  </button>
                  <button
                    type="button"
                    onClick={handleSend}
                    disabled={sendLoading || !draft.trim() || !msg}
                    className="rounded-full border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 text-[11px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-60"
                  >
                    {sendLoading ? "발송 중..." : "이 자동응답 보내기"}
                  </button>
                </div>
              </div>

              {suggestError && (
                <div className="rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">
                  {suggestError}
                </div>
              )}

              <textarea
                className="mt-1 h-32 w-full resize-none rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-[13px] text-slate-50 outline-none focus:border-sky-500/70"
                placeholder="자동응답 제안을 받으면 여기에 내용이 표시됩니다. 직접 작성하거나 수정 후 발송할 수 있습니다."
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />

              {sendResult && (
                <div className="text-[11px] text-slate-400">
                  {sendResult.sent ? (
                    <span className="text-emerald-300">
                      자동응답이 발송되었습니다.
                    </span>
                  ) : (
                    <span className="text-amber-300">
                      자동응답이 발송되지 않았습니다:{" "}
                      {sendResult.skipReason ?? "알 수 없는 이유"}
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* 기존 AutoReply 로그 표시 */}
            {autoReply ? (
              <div className="space-y-2 rounded-lg bg-slate-950 px-3 py-2">
                <div className="mb-1 flex items-center justify-between text-[10px] font-semibold text-slate-400">
                  <span>최근 AutoReply 로그</span>
                  <span>
                    생성:{" "}
                    {new Date(autoReply.created_at).toLocaleString("ko-KR")}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-slate-100">
                  {autoReply.reply_text}
                </p>
                <div className="mt-1 text-[11px] text-slate-500">
                  mode: {autoReply.generation_mode} / send_mode:{" "}
                  {autoReply.send_mode} / sent: {autoReply.sent ? "Y" : "N"}
                </div>
              </div>
            ) : (
              <div className="text-[11px] text-slate-500">
                이 메시지에 대한 AutoReply 로그가 없습니다.
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
};
