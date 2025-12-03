// src/components/MessagesCenter.tsx

import React, { useEffect, useMemo, useState } from "react";

import { messagesApi } from "../api/messages";
import { ApiError } from "../api/client";
import type { MessageActionability, MessageActor, MessageDetail, MessageIntent, MessageListItem, SuggestedReply } from "../types/intents";

const INTENT_LABEL_KO: Partial<Record<MessageIntent, string>> = {
  CHECKIN_QUESTION: "체크인 문의",
  CHECKOUT_QUESTION: "체크아웃 문의",
  RESERVATION_CHANGE: "예약 변경",
  CANCELLATION: "취소/환불",
  COMPLAINT: "클레임/불만",
  LOCATION_QUESTION: "위치/주차",
  AMENITY_QUESTION: "편의시설",
  PET_POLICY_QUESTION: "반려동물 문의",
  GENERAL_QUESTION: "일반 문의",
  THANKS_OR_GOOD_REVIEW: "감사/긍정 피드백",
  OTHER: "기타",
};

const ALL_INTENTS: MessageIntent[] = [
  "CHECKIN_QUESTION",
  "CHECKOUT_QUESTION",
  "RESERVATION_CHANGE",
  "CANCELLATION",
  "COMPLAINT",
  "LOCATION_QUESTION",
  "AMENITY_QUESTION",
  "PET_POLICY_QUESTION",
  "GENERAL_QUESTION",
  "THANKS_OR_GOOD_REVIEW",
  "OTHER",
];

const intentToLabel = (intent: MessageIntent | null): string => {
  if (!intent) return "미분류";
  return INTENT_LABEL_KO[intent] ?? intent;
};

const actorBadge = (actor: MessageActor) => {
  switch (actor) {
    case "guest":
      return "게스트";
    case "host":
      return "호스트";
    case "system":
      return "시스템";
    default:
      return "알수없음";
  }
};

const actionabilityBadge = (a: MessageActionability) => {
  switch (a) {
    case "needs_reply":
      return "답변 필요";
    case "informational":
      return "참고용";
    default:
      return "미정";
  }
};

export const MessagesCenter: React.FC = () => {
  const [messages, setMessages] = useState<MessageListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailMap, setDetailMap] = useState<Record<number, MessageDetail>>({});
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isLoadingReply, setIsLoadingReply] = useState(false);
  const [isSavingIntent, setIsSavingIntent] = useState(false);
  const [replyDraft, setReplyDraft] = useState("");
  const [intentForEdit, setIntentForEdit] = useState<MessageIntent | "">("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const selectedDetail = useMemo(
    () => (selectedId != null ? detailMap[selectedId] : null),
    [selectedId, detailMap]
  );

  // 메시지 리스트 로드
  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setIsLoadingList(true);
        setErrorMessage(null);
        const data = await messagesApi.list();
        if (cancelled) return;
        setMessages(data);
        if (!selectedId && data.length > 0) {
          setSelectedId(data[0].id);
        }
      } catch (err) {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? err.message
            : "메시지 목록을 불러오는 중 오류가 발생했습니다.";
        setErrorMessage(msg);
      } finally {
        if (!cancelled) setIsLoadingList(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // 특정 메시지 상세 로드
  useEffect(() => {
    if (selectedId == null) return;

    // 이미 캐시된 경우 재요청 방지
    if (detailMap[selectedId]) return;

    let cancelled = false;

    const loadDetail = async () => {
      try {
        setIsLoadingDetail(true);
        setErrorMessage(null);
        const data = await messagesApi.detail(selectedId);
        if (cancelled) return;
        setDetailMap((prev) => ({ ...prev, [selectedId]: data }));
        setIntentForEdit(data.intent ?? "");
        setReplyDraft("");
      } catch (err) {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? err.message
            : "메시지 상세를 불러오는 중 오류가 발생했습니다.";
        setErrorMessage(msg);
      } finally {
        if (!cancelled) setIsLoadingDetail(false);
      }
    };

    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedId, detailMap]);

  const handleSelectMessage = (id: number) => {
    setSelectedId(id);
    setReplyDraft("");
  };

  const handleLoadSuggestedReply = async () => {
    if (!selectedDetail) return;

    try {
      setIsLoadingReply(true);
      setErrorMessage(null);
      const data: SuggestedReply = await messagesApi.suggestedReply(
        selectedDetail.id
      );
      setReplyDraft(data.reply_text);

      // Intent 비어있으면 추천 Intent로 채워줌
      setDetailMap((prev) => ({
        ...prev,
        [selectedDetail.id]: {
          ...selectedDetail,
          intent: selectedDetail.intent ?? data.intent,
          intent_confidence:
            selectedDetail.intent_confidence ?? data.intent_confidence,
        },
      }));
      if (!intentForEdit) {
        setIntentForEdit(data.intent);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "추천 답변을 가져오는 중 오류가 발생했습니다.";
      setErrorMessage(msg);
    } finally {
      setIsLoadingReply(false);
    }
  };

  const handleSaveIntent = async () => {
    if (!selectedDetail || !intentForEdit) return;

    try {
      setIsSavingIntent(true);
      setErrorMessage(null);
      await messagesApi.createIntentLabel(selectedDetail.id, intentForEdit);

      // detailMap / messages 동기 업데이트 (최소 상태만 변경)
      setDetailMap((prev) => ({
        ...prev,
        [selectedDetail.id]: {
          ...selectedDetail,
          intent: intentForEdit as MessageIntent,
          intent_confidence: 1.0,
          labels: [
            // 최신 라벨이 가장 위로 오도록
            {
              id: Date.now(), // 실제 ID는 API에서 받을 수 있지만, v0에서는 임시
              intent: intentForEdit as MessageIntent,
              source: "human",
              created_at: new Date().toISOString(),
            },
            ...selectedDetail.labels,
          ],
        },
      }));

      setMessages((prev) =>
        prev.map((m) =>
          m.id === selectedDetail.id
            ? {
                ...m,
                intent: intentForEdit as MessageIntent,
                intent_confidence: 1.0,
              }
            : m
        )
      );
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Intent 라벨을 저장하는 중 오류가 발생했습니다.";
      setErrorMessage(msg);
    } finally {
      setIsSavingIntent(false);
    }
  };

  const handleUseReply = () => {
    if (!replyDraft.trim()) return;
    // v0: 아직 실제 발송은 안 붙이고, 나중에 OTA/API 연동 시 사용할 자리
    alert("아직 실제 발송 기능은 붙지 않았습니다. (v0)");
  };

  return (
    <div className="flex h-screen w-screen bg-slate-50 text-slate-900">
      {/* 왼쪽: 메시지 목록 */}
      <aside className="w-[32%] border-r border-slate-200 flex flex-col">
        <header className="h-14 px-4 border-b border-slate-200 flex items-center justify-between bg-white">
          <div className="flex flex-col">
            <span className="text-sm font-semibold">메시지 센터</span>
            <span className="text-[11px] text-slate-500">
              게스트 문의 + 자동 Intent 분류
            </span>
          </div>
          {isLoadingList && (
            <span className="text-[11px] text-slate-500">불러오는 중…</span>
          )}
        </header>

        <div className="flex-1 overflow-y-auto">
          {messages.map((m) => {
            const isActive = m.id === selectedId;
            return (
              <button
                key={m.id}
                onClick={() => handleSelectMessage(m.id)}
                className={[
                  "w-full text-left px-4 py-3 border-b border-slate-100 transition",
                  isActive ? "bg-slate-100" : "hover:bg-slate-100",
                ].join(" ")}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1">
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-200 text-slate-700">
                      {actorBadge(m.sender_actor)}
                    </span>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                      {actionabilityBadge(m.actionability)}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500">
                    {new Date(m.received_at).toLocaleString()}
                  </span>
                </div>
                <div className="text-[13px] font-medium text-slate-900 truncate">
                  {m.subject || "(제목 없음)"}
                </div>
                <div className="flex items-center gap-1 mt-1">
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                    {intentToLabel(m.intent)}
                  </span>
                  {m.intent_confidence != null && (
                    <span className="text-[10px] text-slate-500">
                      {Math.round(m.intent_confidence * 100)}%
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[11px] text-slate-600 line-clamp-2">
                  {m.preview_text}
                </p>
              </button>
            );
          })}

          {!isLoadingList && messages.length === 0 && (
            <div className="p-4 text-sm text-slate-500">
              표시할 메시지가 없습니다.
            </div>
          )}
        </div>
      </aside>

      {/* 오른쪽: 상세 / Intent / 추천 답변 */}
      <main className="flex-1 flex flex-col">
        <header className="h-14 px-4 border-b border-slate-200 flex items-center justify-between bg-white">
          <div className="flex flex-col">
            <span className="text-sm font-semibold">
              {selectedDetail?.subject || "메시지를 선택하세요"}
            </span>
            {selectedDetail && (
              <span className="text-[11px] text-slate-500">
                {selectedDetail.from_email || "(발신 이메일 없음)"} ·{" "}
                {new Date(selectedDetail.received_at).toLocaleString()}
              </span>
            )}
          </div>
          {errorMessage && (
            <div className="max-w-xs text-[11px] text-red-500 text-right">
              {errorMessage}
            </div>
          )}
        </header>

        {isLoadingDetail && !selectedDetail && (
          <div className="flex-1 flex items-center justify-center text-sm text-slate-500">
            상세 불러오는 중…
          </div>
        )}

        {!isLoadingDetail && !selectedDetail && (
          <div className="flex-1 flex items-center justify-center text-sm text-slate-500">
            왼쪽에서 메시지를 선택하세요.
          </div>
        )}

        {selectedDetail && (
          <div className="flex-1 grid grid-cols-2 min-h-0">
            {/* 좌측: 게스트 메시지 + 원문 */}
            <section className="flex flex-col border-r border-slate-200 min-h-0">
              <div className="p-4 border-b border-slate-200">
                <h3 className="text-xs font-semibold mb-1">
                  게스트 순수 메시지
                </h3>
                <pre className="text-[11px] bg-slate-50 rounded-md p-3 max-h-52 overflow-y-auto whitespace-pre-wrap">
                  {selectedDetail.pure_guest_message ||
                    "(추출된 게스트 메시지가 없습니다)"}
                </pre>
              </div>
              <div className="p-4 flex-1 min-h-0">
                <h3 className="text-xs font-semibold mb-1">
                  이메일 원문 (텍스트)
                </h3>
                <pre className="text-[11px] bg-slate-50 rounded-md p-3 h-full overflow-y-auto whitespace-pre-wrap">
                  {selectedDetail.text_body || "(텍스트 본문 없음)"}
                </pre>
              </div>
            </section>

            {/* 우측: Intent / 라벨 / 추천 답변 */}
            <section className="flex flex-col min-h-0">
              {/* Intent & 라벨 */}
              <div className="p-4 border-b border-slate-200 space-y-3">
                <h3 className="text-xs font-semibold">Intent & 라벨</h3>

                <div className="flex items-start gap-6">
                  <div>
                    <div className="text-[11px] text-slate-500 mb-1">
                      현재 시스템 Intent
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                        {intentToLabel(selectedDetail.intent)}
                      </span>
                      {selectedDetail.intent_confidence != null && (
                        <span className="text-[10px] text-slate-500">
                          {Math.round(
                            selectedDetail.intent_confidence * 100
                          )}
                          %
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="text-[11px] text-slate-500 mb-1">
                      Intent 수정
                    </div>
                    <div className="flex items-center gap-2">
                      <select
                        className="text-[11px] border rounded-md px-2 py-1 bg-white"
                        value={intentForEdit ?? ""}
                        onChange={(e) =>
                          setIntentForEdit(
                            (e.target.value || "") as MessageIntent | ""
                          )
                        }
                      >
                        <option value="">선택 안 함</option>
                        {ALL_INTENTS.map((it) => (
                          <option key={it} value={it}>
                            {intentToLabel(it)}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={handleSaveIntent}
                        disabled={!intentForEdit || isSavingIntent}
                        className="text-[11px] px-3 py-1 rounded-md bg-slate-900 text-white disabled:opacity-50"
                      >
                        {isSavingIntent ? "저장 중…" : "라벨 저장"}
                      </button>
                    </div>
                  </div>
                </div>

                <div>
                  <div className="text-[11px] text-slate-500 mb-1">
                    라벨 히스토리
                  </div>
                  <div className="max-h-24 overflow-y-auto text-[11px] bg-slate-50 rounded-md p-2 space-y-1">
                    {selectedDetail.labels.length === 0 && (
                      <div className="text-slate-400">
                        라벨 히스토리가 없습니다.
                      </div>
                    )}
                    {selectedDetail.labels.map((l) => (
                      <div
                        key={l.id}
                        className="flex justify-between gap-3"
                      >
                        <span className="truncate">
                          [{l.source}] {intentToLabel(l.intent)}
                        </span>
                        <span className="text-slate-400 shrink-0">
                          {new Date(l.created_at).toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* 추천 답변 */}
              <div className="flex-1 p-4 flex flex-col min-h-0">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-semibold">추천 답변</h3>
                  <button
                    onClick={handleLoadSuggestedReply}
                    disabled={isLoadingReply}
                    className="text-[11px] px-3 py-1 rounded-md border border-slate-300 bg-white hover:bg-slate-50 disabled:opacity-50"
                  >
                    {isLoadingReply ? "불러오는 중…" : "추천 불러오기"}
                  </button>
                </div>
                <textarea
                  className="flex-1 text-[11px] border rounded-md p-3 bg-white resize-none focus:outline-none focus:ring focus:ring-slate-200"
                  placeholder="추천 답변을 불러오거나 직접 입력하세요."
                  value={replyDraft}
                  onChange={(e) => setReplyDraft(e.target.value)}
                />
                <div className="mt-2 flex justify-end">
                  <button
                    onClick={handleUseReply}
                    disabled={!replyDraft.trim()}
                    className="text-[11px] px-4 py-1.5 rounded-md bg-emerald-600 text-white disabled:opacity-50"
                  >
                    이 답변으로 응답하기 (v0)
                  </button>
                </div>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
};
