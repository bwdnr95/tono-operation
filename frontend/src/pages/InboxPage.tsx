// src/pages/InboxPage.tsx
import React from "react";
import { useSearchParams } from "react-router-dom";
import { bulkSend } from "../api/conversations";
import type { ConversationDetailDTO, ConversationListItemDTO } from "../types/conversations";
import type { RiskSignalDTO, ConflictDTO } from "../types/commitments";
import { ConversationDetail } from "../components/conversations/ConversationDetail";
import { RoomAssignmentModal } from "../components/conversations/RoomAssignmentModal";
import { canBulkSend } from "../components/conversations/OutcomeLabelDisplay";
import {
  generateDraftReply,
  getBulkEligibleConversations,
  getConversationDetail,
  getConversations,
  patchDraftReply,
  sendConversation,
  ingestGmailMessages,
  markConversationRead,
} from "../api/conversations";
import { getRiskSignals, resolveRiskSignal, checkDraftConflicts } from "../api/commitments";
import { useConversationStore } from "../store/conversationStore";
import { SkeletonConversationList, SkeletonConversationDetail } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { useWebSocket } from "../hooks/useWebSocket";

function isoNowMinusHours(h: number) {
  return new Date(Date.now() - h * 60 * 60 * 1000).toISOString();
}

function formatTime(v: string) {
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

type BulkRow = {
  conversation_id: string;
  airbnb_thread_id: string;
  selected: boolean;
  guest_name?: string | null;
  checkin_date?: string | null;
  checkout_date?: string | null;
  draft_content?: string | null;
  outcome_label?: any | null;
};

type BulkSendRowResult = {
  conversation_id: string;
  airbnb_thread_id: string;
  result: "sent" | "skipped" | "failed";
  message?: string;
};

export const InboxPage: React.FC = () => {
  // Toast
  const { showToast } = useToast();

  // Store
  const {
    allConversations,
    conversationDetails,
    isReadFilter,
    statusFilter,
    safetyFilter,
    threadIdFilter,
    sendActionFilter,
    selectedId,
    isInitialized,
    listLoading,
    detailLoading,
    error: storeError,
    setAllConversations,
    setConversationDetail,
    setIsReadFilter,
    setStatusFilter,
    setSafetyFilter,
    setThreadIdFilter,
    setSendActionFilter,
    setSelectedId,
    setListLoading,
    setDetailLoading,
    setError: setStoreError,
    markAsRead,
    getFilteredConversations,
    clearAllConversationDetails,
    syncDetailToList,
    getCachedDetail,
    isDetailStale,
  } = useConversationStore();

  const filteredItems = getFilteredConversations();

  // Local state
  const [detail, setDetail] = React.useState<ConversationDetailDTO | null>(null);
  const [detailError, setDetailError] = React.useState<string | null>(null);
  const [draftContent, setDraftContent] = React.useState("");
  const [generating, setGenerating] = React.useState(false);
  const [generateStep, setGenerateStep] = React.useState(0);
  const [saving, setSaving] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [lastActionMsg, setLastActionMsg] = React.useState<string | null>(null);

  // Mobile: chat panel open state
  const [mobileChatOpen, setMobileChatOpen] = React.useState(false);

  // Bulk
  const [bulkOpen, setBulkOpen] = React.useState(false);
  const [bulkLoading, setBulkLoading] = React.useState(false);
  const [bulkError, setBulkError] = React.useState<string | null>(null);
  const [bulkRows, setBulkRows] = React.useState<BulkRow[]>([]);
  const [bulkSending, setBulkSending] = React.useState(false);
  const [bulkResults, setBulkResults] = React.useState<BulkSendRowResult[] | null>(null);

  // Gmail
  const [ingesting, setIngesting] = React.useState(false);
  const [ingestResult, setIngestResult] = React.useState<string | null>(null);
  const [ingestStep, setIngestStep] = React.useState(0);

  // Risk/Conflict
  const [riskSignals, setRiskSignals] = React.useState<RiskSignalDTO[]>([]);
  const [riskSignalsLoading, setRiskSignalsLoading] = React.useState(false);
  const [conflicts, setConflicts] = React.useState<ConflictDTO[]>([]);
  const [showConflictModal, setShowConflictModal] = React.useState(false);
  const [pendingSend, setPendingSend] = React.useState(false);

  // 🆕 Room Assignment (객실 배정)
  const [showRoomAssignmentModal, setShowRoomAssignmentModal] = React.useState(false);

  // URL params
  const [searchParams, setSearchParams] = useSearchParams();
  const [highlightedId, setHighlightedId] = React.useState<string | null>(
    searchParams.get("conversation_id")
  );

  // ===== URL conversation_id 또는 thread 파라미터 처리 =====
  React.useEffect(() => {
    const conversationIdFromUrl = searchParams.get("conversation_id");
    const threadIdFromUrl = searchParams.get("thread"); // airbnb_thread_id
    
    if (allConversations.length === 0) return;
    
    let targetConversation = null;
    
    // conversation_id로 찾기
    if (conversationIdFromUrl) {
      targetConversation = allConversations.find(c => c.id === conversationIdFromUrl);
    }
    // thread (airbnb_thread_id)로 찾기
    else if (threadIdFromUrl) {
      targetConversation = allConversations.find(c => c.airbnb_thread_id === threadIdFromUrl);
    }
    
    if (targetConversation) {
      setSelectedId(targetConversation.id);
      setHighlightedId(targetConversation.id);
      // URL 파라미터 제거 (선택 후)
      searchParams.delete("conversation_id");
      searchParams.delete("thread");
      setSearchParams(searchParams, { replace: true });
      // 3초 후 하이라이트 제거
      const timer = setTimeout(() => setHighlightedId(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [searchParams, allConversations]);

  // ===== Initial Load =====
  // 페이지 진입 시 항상 최신 데이터를 가져옴
  // isInitialized는 로딩 중 빈 화면 방지용으로만 사용 (캐시된 데이터 표시)
  React.useEffect(() => {
    const fetchAll = async () => {
      // 캐시가 없을 때만 로딩 표시 (있으면 백그라운드에서 갱신)
      if (!isInitialized) {
        setListLoading(true);
      }
      try {
        const res = await getConversations({
          channel: "gmail",
          limit: 200,
        });
        setAllConversations(res.items);
        
        // 첫 로드 시에만 자동 선택
        if (!isInitialized && res.items.length > 0) {
          // URL에 conversation_id 또는 thread가 있으면 그걸 먼저 선택
          const conversationIdFromUrl = searchParams.get("conversation_id");
          const threadIdFromUrl = searchParams.get("thread");
          
          let targetConversation = null;
          if (conversationIdFromUrl) {
            targetConversation = res.items.find(c => c.id === conversationIdFromUrl);
          } else if (threadIdFromUrl) {
            targetConversation = res.items.find(c => c.airbnb_thread_id === threadIdFromUrl);
          }
          
          if (targetConversation) {
            setSelectedId(targetConversation.id);
            setHighlightedId(targetConversation.id);
            // URL 파라미터 제거
            searchParams.delete("conversation_id");
            searchParams.delete("thread");
            setSearchParams(searchParams, { replace: true });
            // 3초 후 하이라이트 제거
            setTimeout(() => setHighlightedId(null), 3000);
            return;
          }
          
          // URL에 없으면 첫번째 unread 또는 첫번째 항목
          const firstUnread = res.items.find(c => !c.is_read);
          setSelectedId(firstUnread?.id || res.items[0].id);
        }
      } catch (e: any) {
        setStoreError(e?.message ?? "목록 조회 실패");
      } finally {
        setListLoading(false);
      }
    };
    fetchAll();
  }, []); // 페이지 마운트 시 1회 실행

  // ===== WebSocket: 스케줄러 완료 시 자동 새로고침 =====
  useWebSocket({
    onRefresh: async (scope, reason) => {
      if (scope === 'conversations' || scope === 'all') {
        console.log(`[WebSocket] Refreshing conversations (reason: ${reason})`);
        // 로딩 중이 아닐 때만 새로고침
        if (!listLoading) {
          try {
            const res = await getConversations({ channel: "gmail", limit: 200 });
            setAllConversations(res.items);
            // 캐시된 detail도 무효화 (다음 선택 시 새로 fetch)
            clearAllConversationDetails();
            showToast({ 
              type: "info", 
              title: "새 메시지", 
              message: "새로운 메시지가 도착했습니다" 
            });
          } catch (e) {
            console.error("WebSocket refresh failed:", e);
          }
        }
      }
    },
    onConnected: () => {
      console.log("[WebSocket] Connected to server");
    },
    onDisconnected: () => {
      console.log("[WebSocket] Disconnected from server");
    },
  });

  // ===== 탭 포커스 시 새로고침 (WebSocket 연결 끊겼을 때 백업) =====
  React.useEffect(() => {
    let lastRefresh = Date.now();
    const MIN_REFRESH_GAP = 60 * 1000; // 최소 1분 간격 (WebSocket이 있으므로 늘림)
    
    const handleVisibilityChange = async () => {
      if (document.visibilityState === "visible") {
        const now = Date.now();
        // 마지막 새로고침 후 1분 이상 지났을 때만
        if (now - lastRefresh > MIN_REFRESH_GAP && !listLoading) {
          lastRefresh = now;
          try {
            const res = await getConversations({ channel: "gmail", limit: 200 });
            setAllConversations(res.items);
          } catch (e) {
            console.error("Visibility refresh failed:", e);
          }
        }
      }
    };
    
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [listLoading]);

  // ===== Detail Load (with stale check) =====
  React.useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    
    // 캐시가 있고 stale하지 않으면 캐시 사용
    const cached = getCachedDetail(selectedId);
    const stale = isDetailStale(selectedId);
    
    if (cached && !stale) {
      setDetail(cached);
      setDraftContent(cached.draft_reply?.content ?? "");
      // Risk signals도 캐시된 데이터 기반으로 로드
      if (cached.conversation?.airbnb_thread_id) {
        getRiskSignals(cached.conversation.airbnb_thread_id)
          .then(res => setRiskSignals(res.signals || []))
          .catch(() => {});
      }
      return;
    }
    
    // 캐시 없거나 stale → API 호출
    const fetchDetail = async () => {
      setDetailLoading(true);
      setDetailError(null);
      setRiskSignals([]);
      try {
        const d = await getConversationDetail(selectedId);
        setDetail(d);
        setConversationDetail(selectedId, d);
        syncDetailToList(selectedId, d); // List도 동기화
        setDraftContent(d.draft_reply?.content ?? "");
        if (d.conversation?.airbnb_thread_id) {
          try {
            const signalRes = await getRiskSignals(d.conversation.airbnb_thread_id);
            setRiskSignals(signalRes.signals || []);
          } catch {}
        }
      } catch (e: any) {
        setDetailError(e?.message ?? "상세 조회 실패");
      } finally {
        setDetailLoading(false);
      }
    };
    fetchDetail();
  }, [selectedId]); // conversationDetails 의존성 제거 (무한루프 방지)

  // ===== Actions =====
  const onTabChange = (tab: boolean | null) => {
    setIsReadFilter(tab);
    const filtered = allConversations
      .filter(c => (tab === null ? true : c.is_read === tab))
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    if (filtered.length > 0) setSelectedId(filtered[0].id);
    else setSelectedId(null);
  };

  const onRefresh = async () => {
    setListLoading(true);
    // 캐시된 상세 데이터 모두 클리어 → 최신 데이터로 다시 fetch
    clearAllConversationDetails();
    setDetail(null);
    try {
      const res = await getConversations({ channel: "gmail", limit: 200 });
      setAllConversations(res.items);
    } catch (e: any) {
      setStoreError(e?.message ?? "새로고침 실패");
    } finally {
      setListLoading(false);
    }
  };

  const onGenerateDraft = async () => {
    if (!detail) return;
    setGenerating(true);
    setGenerateStep(0);
    
    // 단계별 애니메이션 타이머
    const stepTimer = setInterval(() => {
      setGenerateStep(prev => (prev < 3 ? prev + 1 : prev));
    }, 1200);
    
    try {
      const res = await generateDraftReply(detail.conversation.id);
      clearInterval(stepTimer);
      setDraftContent(res.draft_reply?.content ?? "");
      setLastActionMsg("초안 생성 완료");
      showToast({ type: "success", title: "초안 생성 완료", message: "AI가 답변을 생성했습니다" });
      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
      setConversationDetail(detail.conversation.id, refreshed);
      syncDetailToList(detail.conversation.id, refreshed); // List 동기화
    } catch (e: any) {
      clearInterval(stepTimer);
      setDetailError(e?.message ?? "초안 생성 실패");
      showToast({ type: "error", title: "초안 생성 실패", message: e?.message });
    } finally {
      setGenerating(false);
      setGenerateStep(0);
    }
  };

  const onSaveDraft = async () => {
    if (!detail || !draftContent.trim()) return;
    setSaving(true);
    try {
      await patchDraftReply(detail.conversation.id, draftContent);
      setLastActionMsg("초안 저장 완료");
      showToast({ type: "success", title: "저장됨", message: "초안이 저장되었습니다" });
      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
      setConversationDetail(detail.conversation.id, refreshed);
      syncDetailToList(detail.conversation.id, refreshed); // List 동기화
    } catch (e: any) {
      setDetailError(e?.message ?? "초안 저장 실패");
      showToast({ type: "error", title: "저장 실패", message: e?.message });
    } finally {
      setSaving(false);
    }
  };

  const executeSend = async () => {
    if (!detail) return;
    setSending(true);
    try {
      await sendConversation(detail.conversation.id, { draft_reply_id: detail.draft_reply!.id });
      setLastActionMsg("발송 완료");
      showToast({ 
        type: "success", 
        title: "발송 완료!", 
        message: `${detail.conversation.guest_name || "게스트"}님께 메시지가 전송되었습니다` 
      });
      // 발송 후 해당 detail과 list를 새로고침
      const refreshed = await getConversationDetail(detail.conversation.id);
      setDetail(refreshed);
      setConversationDetail(detail.conversation.id, refreshed);
      syncDetailToList(detail.conversation.id, refreshed); // List 동기화
      // 전체 list도 새로고침 (다른 대화 상태도 변경되었을 수 있음)
      const listRes = await getConversations({ channel: "gmail", limit: 200 });
      setAllConversations(listRes.items);
    } catch (e: any) {
      setDetailError(e?.message ?? "발송 실패");
      showToast({ type: "error", title: "발송 실패", message: e?.message });
    } finally {
      setSending(false);
    }
  };

  const onSend = async () => {
    if (!detail?.draft_reply?.id) return;
    if (detail.draft_reply.safety_status === "block") {
      setDetailError("safety_status가 block이므로 발송 불가");
      return;
    }
    if (detail.conversation.status !== "ready_to_send" && detail.conversation.status !== "blocked") {
      setDetailError("status가 ready_to_send가 아님");
      return;
    }
    try {
      const conflictRes = await checkDraftConflicts(detail.conversation.airbnb_thread_id, draftContent);
      if (conflictRes.has_any_conflict) {
        setConflicts(conflictRes.conflicts);
        setShowConflictModal(true);
        return;
      }
    } catch {}
    await executeSend();
  };

  const onMarkRead = async () => {
    if (!detail) return;
    markAsRead(detail.conversation.id);
    setLastActionMsg("처리완료");
    try {
      await markConversationRead(detail.conversation.id);
    } catch {}
  };

  const onDismissRiskSignal = async (signalId: string) => {
    if (!detail?.conversation?.airbnb_thread_id) return;
    try {
      await resolveRiskSignal(detail.conversation.airbnb_thread_id, signalId);
      setRiskSignals(prev => prev.filter(s => s.id !== signalId));
    } catch {}
  };

  const onIngestGmail = async () => {
    setIngesting(true);
    setIngestResult(null);
    setIngestStep(0);
    
    // 단계별 애니메이션 타이머
    const stepTimer = setInterval(() => {
      setIngestStep(prev => (prev < 3 ? prev + 1 : prev));
    }, 1500);
    
    try {
      const res = await ingestGmailMessages();
      clearInterval(stepTimer);
      setIngestStep(4); // 완료 단계
      setIngestResult(`✓ ${res.total_conversations}개 대화 처리됨`);
      showToast({ 
        type: "success", 
        title: "메일 불러오기 완료", 
        message: `${res.total_conversations}개 대화가 처리되었습니다` 
      });
      await onRefresh();
    } catch (e: any) {
      clearInterval(stepTimer);
      setIngestResult(`✗ 실패: ${e?.message}`);
      showToast({ type: "error", title: "메일 불러오기 실패", message: e?.message });
    } finally {
      setIngesting(false);
      setIngestStep(0);
    }
  };

  // ===== Bulk =====
  const openBulk = async () => {
    setBulkOpen(true);
    setBulkLoading(true);
    setBulkError(null);
    setBulkResults(null);
    try {
      const res = await getBulkEligibleConversations();
      const rows = await Promise.all(
        res.items.map(async (it) => {
          try {
            const d = await getConversationDetail(it.id);
            return {
              conversation_id: it.id,
              airbnb_thread_id: it.airbnb_thread_id,
              selected: canBulkSend(d.draft_reply?.outcome_label),
              guest_name: d.messages?.find(m => m.guest_name)?.guest_name ?? it.guest_name,
              checkin_date: it.checkin_date,
              checkout_date: it.checkout_date,
              draft_content: d.draft_reply?.content ?? null,
              outcome_label: d.draft_reply?.outcome_label ?? null,
            };
          } catch {
            return {
              conversation_id: it.id,
              airbnb_thread_id: it.airbnb_thread_id,
              selected: true,
              guest_name: it.guest_name,
              checkin_date: it.checkin_date,
              checkout_date: it.checkout_date,
              draft_content: null,
              outcome_label: null,
            };
          }
        })
      );
      setBulkRows(rows);
    } catch (e: any) {
      setBulkError(e?.message ?? "Bulk 조회 실패");
    } finally {
      setBulkLoading(false);
    }
  };

  const runBulkSend = async () => {
    const selected = bulkRows.filter(r => r.selected);
    if (!selected.length) {
      setBulkError("선택된 대화가 없습니다");
      return;
    }
    setBulkSending(true);
    try {
      const res = await bulkSend(selected.map(r => r.conversation_id));
      setBulkResults(res.results.map(r => ({
        conversation_id: r.conversation_id,
        airbnb_thread_id: selected.find(s => s.conversation_id === r.conversation_id)?.airbnb_thread_id ?? "",
        result: r.result,
        message: r.error_message ?? undefined,
      })));
      await onRefresh();
    } catch (e: any) {
      setBulkError(e?.message ?? "Bulk send 실패");
    } finally {
      setBulkSending(false);
    }
  };

  // ===== Render =====
  const unreadCount = allConversations.filter(c => !c.is_read).length;
  const readCount = allConversations.filter(c => c.is_read).length;
  const autoSentCount = allConversations.filter(c => c.last_send_action === "auto_sent").length;

  return (
    <div className="inbox-page" style={{ display: "flex", flexDirection: "column", height: "100%", position: "relative" }}>
      {/* Loading Overlay for Gmail Ingest */}
      {ingesting && (
        <div className="inbox-loading-overlay">
          <div className="inbox-loading-card">
            <div className="inbox-loading-icon">
              {ingestStep === 0 && "📡"}
              {ingestStep === 1 && "📬"}
              {ingestStep === 2 && "🔍"}
              {ingestStep >= 3 && "⚙️"}
            </div>
            <p className="inbox-loading-text">
              {ingestStep === 0 && "Gmail 연결 중..."}
              {ingestStep === 1 && "메일 불러오는 중..."}
              {ingestStep === 2 && "대화 분석 중..."}
              {ingestStep >= 3 && "데이터 처리 중..."}
            </p>
            <div className="inbox-loading-steps">
              {[0, 1, 2, 3].map(step => (
                <div key={step} className={`inbox-loading-step ${step <= ingestStep ? "active" : ""}`} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* AI 생성 중 오버레이 */}
      {generating && (
        <div className="inbox-loading-overlay">
          <div className="inbox-loading-card">
            <div className="inbox-loading-icon">
              {generateStep === 0 && "💭"}
              {generateStep === 1 && "🏠"}
              {generateStep === 2 && "✍️"}
              {generateStep >= 3 && "🔍"}
            </div>
            <p className="inbox-loading-text">
              {generateStep === 0 && "대화 내용 분석 중..."}
              {generateStep === 1 && "숙소 정보 확인 중..."}
              {generateStep === 2 && "답변 생성 중..."}
              {generateStep >= 3 && "검토 중..."}
            </p>
            <div className="inbox-loading-steps">
              {[0, 1, 2, 3].map(step => (
                <div key={step} className={`inbox-loading-step ${step <= generateStep ? "active" : ""}`} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ===== Top Header Bar (Full Width) ===== */}
      <div className="inbox-top-header">
        <div className="inbox-top-header-left">
          <h1 className="inbox-page-title">Inbox</h1>
          <span className="inbox-list-title-badge">{filteredItems.length}</span>
          
          {/* Search */}
          <div className="inbox-search" style={{ marginLeft: "24px", width: "280px" }}>
            <svg className="inbox-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              type="text"
              value={threadIdFilter}
              onChange={(e) => setThreadIdFilter(e.target.value)}
              placeholder="게스트명, 숙소코드 검색..."
              className="inbox-search-input"
            />
          </div>
        </div>

        <div className="inbox-top-header-right">
          <button onClick={onRefresh} disabled={listLoading} className="inbox-btn inbox-btn-ghost inbox-btn-sm">
            {listLoading ? "⟳" : "↻"} 새로고침
          </button>
          <button onClick={onIngestGmail} disabled={ingesting} className="inbox-btn inbox-btn-ghost inbox-btn-sm">
            📥 메일
          </button>
          <button onClick={openBulk} className="inbox-btn inbox-btn-primary inbox-btn-sm">
            Bulk Send
          </button>
        </div>
      </div>

      {/* ===== Filter & Stats Row (Full Width) ===== */}
      <div className="inbox-filter-row">
        {/* Filter Tabs */}
        <div className="inbox-filter-tabs">
          <button 
            onClick={() => onTabChange(false)} 
            className={`inbox-filter-tab ${isReadFilter === false ? "active" : ""}`}
          >
            안읽음
            {unreadCount > 0 && <span className="inbox-filter-tab-count">{unreadCount}</span>}
          </button>
          <button 
            onClick={() => onTabChange(true)} 
            className={`inbox-filter-tab ${isReadFilter === true ? "active" : ""}`}
          >
            완료
          </button>
          <button 
            onClick={() => onTabChange(null)} 
            className={`inbox-filter-tab ${isReadFilter === null ? "active" : ""}`}
          >
            전체
          </button>
        </div>

        {/* Stats */}
        <div className="inbox-stats-inline">
          <div className="inbox-stat-inline">
            <span className="inbox-stat-label">안읽음</span>
            <span className="inbox-stat-value warning">{unreadCount}</span>
          </div>
          <div className="inbox-stat-inline">
            <span className="inbox-stat-label">처리완료</span>
            <span className="inbox-stat-value success">{readCount}</span>
          </div>
          <div 
            className={`inbox-stat-inline clickable ${sendActionFilter === "auto_sent" ? "active" : ""}`}
            onClick={() => setSendActionFilter(sendActionFilter === "auto_sent" ? "" : "auto_sent")}
            title="클릭하여 자동발송만 보기"
          >
            <span className="inbox-stat-label">🤖 자동발송</span>
            <span className="inbox-stat-value primary">{autoSentCount}</span>
          </div>
        </div>

        {/* Filters */}
        <div className="inbox-filters-inline">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="inbox-filter-select">
            <option value="">상태 전체</option>
            <option value="open">대기중</option>
            <option value="needs_review">검토필요</option>
            <option value="ready_to_send">발송준비</option>
            <option value="sent">발송완료</option>
            <option value="blocked">실패</option>
          </select>
          <select value={safetyFilter} onChange={(e) => setSafetyFilter(e.target.value)} className="inbox-filter-select">
            <option value="">Safety</option>
            <option value="pass">Pass</option>
            <option value="review">Review</option>
            <option value="block">Block</option>
          </select>
        </div>
      </div>

      {/* ===== Main Content (3 Columns) ===== */}
      <div className={`inbox-container ${mobileChatOpen ? "chat-open" : ""}`}>
        {/* Left Panel: Conversation List */}
        <div className="inbox-list-panel">
          <div className="inbox-conversation-list">
            {listLoading ? (
              <SkeletonConversationList count={6} />
            ) : filteredItems.length === 0 ? (
              <div className="inbox-empty-state">
                <div className="inbox-empty-state-icon">📭</div>
                <div className="inbox-empty-state-title">대화가 없습니다</div>
                <div className="inbox-empty-state-text">필터를 변경하거나 메일을 불러오세요</div>
              </div>
            ) : (
              filteredItems.map(item => {
                const isHighlighted = item.id === highlightedId;
                const isUnread = !item.is_read;
                return (
                  <div
                    key={item.id}
                    onClick={() => {
                      setSelectedId(item.id);
                      setMobileChatOpen(true); // 모바일에서 채팅 패널 열기
                    }}
                    className={`inbox-conversation-item ${item.id === selectedId ? "selected" : ""} ${isUnread ? "unread" : ""}`}
                    style={{
                      boxShadow: isHighlighted ? "0 0 0 2px var(--primary), var(--shadow-md)" : undefined,
                    }}
                  >
                    <div className={`inbox-avatar ${isUnread ? "unread" : ""}`}>
                      {item.guest_name?.charAt(0) || "?"}
                    </div>
                    <div className="inbox-conversation-content">
                      <div className="inbox-conversation-header">
                        <span className="inbox-conversation-name">
                          {item.guest_name || "게스트"}
                        </span>
                        {item.reservation_status === "inquiry" && (
                          <span className="inbox-status-badge" style={{ background: "var(--primary-bg)", color: "var(--primary)" }}>
                            💬 문의
                          </span>
                        )}
                        {item.property_code && (
                          <span className="inbox-conversation-property">
                            {item.property_code}
                          </span>
                        )}
                      </div>
                      {item.checkin_date && item.checkout_date && (
                        <div className="inbox-conversation-dates">
                          {item.checkin_date} → {item.checkout_date}
                        </div>
                      )}
                      <div className="inbox-conversation-meta">
                        <span className={`inbox-status-badge ${
                          item.status === "ready_to_send" ? "ready" : 
                          item.status === "needs_review" ? "review" : 
                          item.status === "blocked" ? "blocked" : 
                          item.status === "sent" ? "sent" : ""
                        }`}>
                          {item.status === "ready_to_send" ? "발송준비" : 
                           item.status === "needs_review" ? "검토필요" : 
                           item.status === "sent" ? "완료" : 
                           item.status === "blocked" ? "실패" : "대기"}
                        </span>
                        {item.status === "sent" && item.last_send_action === "auto_sent" && (
                          <span className="inbox-status-badge auto">🤖 자동</span>
                        )}
                        <span className="inbox-conversation-time">{formatTime(item.updated_at)}</span>
                      </div>
                    </div>
                    {isUnread && <div className="inbox-unread-dot" />}
                  </div>
                );
              })
            )}
          </div>

          {storeError && (
            <div style={{ padding: "12px 20px", color: "var(--danger)", fontSize: "13px", background: "var(--danger-bg)" }}>
              {storeError}
            </div>
          )}
        </div>

      {/* ===== Center Panel: Chat Detail ===== */}
      <div className="inbox-chat-panel">
        {/* Mobile Back Button - 채팅 패널 내부 상단 고정 */}
        <button 
          className="mobile-chat-back-btn"
          onClick={() => setMobileChatOpen(false)}
          aria-label="목록으로 돌아가기"
        >
          ←
        </button>
        
        {detailLoading ? (
          <SkeletonConversationDetail />
        ) : detailError ? (
          <div className="inbox-empty-state">
            <div className="inbox-empty-state-icon">⚠️</div>
            <div className="inbox-empty-state-text">{detailError}</div>
          </div>
        ) : !detail ? (
          <div className="inbox-empty-state">
            <div className="inbox-empty-state-icon">💬</div>
            <div className="inbox-empty-state-title">대화를 선택해주세요</div>
            <div className="inbox-empty-state-text">왼쪽 목록에서 대화를 선택하면 상세 내용이 표시됩니다</div>
          </div>
        ) : (
          <ConversationDetail
            detail={detail}
            loading={detailLoading}
            error={detailError}
            draftContent={draftContent}
            onChangeDraftContent={setDraftContent}
            onGenerateDraft={onGenerateDraft}
            onSaveDraft={onSaveDraft}
            onSend={onSend}
            generating={generating}
            saving={saving}
            sending={sending}
            lastActionMsg={lastActionMsg}
            onMarkRead={onMarkRead}
            riskSignals={riskSignals}
            riskSignalsLoading={riskSignalsLoading}
            onDismissRiskSignal={onDismissRiskSignal}
            conflicts={conflicts}
            showConflictModal={showConflictModal}
            onConfirmSendWithConflict={() => { setShowConflictModal(false); executeSend(); }}
            onCancelSendWithConflict={() => setShowConflictModal(false)}
            onOpenRoomAssignment={() => setShowRoomAssignmentModal(true)}
          />
        )}
      </div>

      {/* ===== Right Panel: Info Sidebar ===== */}
      {detail && (
        <div className="inbox-info-panel">
          <div className="inbox-info-header">
            <h3>예약 정보</h3>
          </div>

          {/* Guest Info */}
          <div className="inbox-info-section">
            <div className="inbox-info-section-title">게스트</div>
            <div className="inbox-info-row">
              <span className="inbox-info-label">이름</span>
              <span className="inbox-info-value">{detail.conversation.guest_name || "-"}</span>
            </div>
            <div className="inbox-info-row">
              <span className="inbox-info-label">상태</span>
              <span className="inbox-info-value">
                {detail.conversation.reservation_status === "inquiry" ? "💬 문의" :
                 detail.conversation.reservation_status === "awaiting_approval" ? "⏳ 예약 요청" :
                 detail.conversation.reservation_status === "confirmed" ? "✅ 예약확정" :
                 detail.conversation.reservation_status === "canceled" ? "❌ 취소됨" :
                 detail.conversation.reservation_status === "declined" ? "🚫 거절됨" :
                 detail.conversation.reservation_status === "expired" ? "⏰ 만료됨" :
                 detail.conversation.reservation_status === "alteration_requested" ? "🔄 변경 요청" :
                 detail.conversation.reservation_status ? detail.conversation.reservation_status : "📝 정보없음"}
              </span>
            </div>
          </div>

          {/* Reservation Info */}
          <div className="inbox-info-section">
            <div className="inbox-info-section-title">예약 상세</div>
            <div className="inbox-info-row">
              <span className="inbox-info-label">숙소</span>
              <span className="inbox-info-value">{detail.conversation.property_code || "-"}</span>
            </div>
            <div className="inbox-info-row">
              <span className="inbox-info-label">체크인</span>
              <span className="inbox-info-value">{detail.conversation.checkin_date || "-"}</span>
            </div>
            <div className="inbox-info-row">
              <span className="inbox-info-label">체크아웃</span>
              <span className="inbox-info-value">{detail.conversation.checkout_date || "-"}</span>
            </div>
          </div>

          {/* Status Info */}
          <div className="inbox-info-section">
            <div className="inbox-info-section-title">처리 상태</div>
            <div className="inbox-info-row">
              <span className="inbox-info-label">상태</span>
              <span className={`inbox-status-badge ${
                detail.conversation.status === "ready_to_send" ? "ready" : 
                detail.conversation.status === "needs_review" ? "review" : 
                detail.conversation.status === "blocked" ? "blocked" : "sent"
              }`}>
                {detail.conversation.status === "ready_to_send" ? "발송준비" : 
                 detail.conversation.status === "needs_review" ? "검토필요" : 
                 detail.conversation.status === "sent" ? "완료" : 
                 detail.conversation.status === "blocked" ? "실패" : "대기"}
              </span>
            </div>
            <div className="inbox-info-row">
              <span className="inbox-info-label">Safety</span>
              <span className={`inbox-status-badge ${
                detail.conversation.safety_status === "pass" ? "ready" : 
                detail.conversation.safety_status === "review" ? "review" : "blocked"
              }`}>
                {detail.conversation.safety_status === "pass" ? "안전" : 
                 detail.conversation.safety_status === "review" ? "검토" : "차단"}
              </span>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="inbox-info-section">
            <div className="inbox-info-section-title">빠른 액션</div>
            <div className="inbox-quick-actions">
              {detail.conversation.airbnb_thread_id && (
                <a
                  href={`https://www.airbnb.co.kr/hosting/thread/${detail.conversation.airbnb_thread_id}?thread_type=home_booking`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inbox-quick-action"
                  style={{ textDecoration: "none" }}
                >
                  <div className="inbox-quick-action-icon" style={{ background: "var(--danger-bg)", color: "#FF385C" }}>
                    🏠
                  </div>
                  <span>에어비앤비에서 보기</span>
                </a>
              )}
              {detail.conversation.can_reassign && (
                <button
                  onClick={() => setShowRoomAssignmentModal(true)}
                  className="inbox-quick-action"
                >
                  <div className="inbox-quick-action-icon">🛏️</div>
                  <span>객실 배정</span>
                </button>
              )}
              <button onClick={onMarkRead} className="inbox-quick-action">
                <div className="inbox-quick-action-icon" style={{ background: "var(--success-bg)", color: "var(--success)" }}>✓</div>
                <span>처리완료 표시</span>
              </button>
            </div>
          </div>
        </div>
      )}
      </div> {/* End of inbox-container */}

      {/* Bulk Modal */}
      {bulkOpen && (
        <div className="modal-overlay">
          <div className="modal" style={{ maxWidth: "700px" }}>
            <div className="modal-header">
              <h2 className="modal-title">Bulk Send</h2>
              <button onClick={() => setBulkOpen(false)} className="inbox-btn inbox-btn-ghost inbox-btn-sm">✕</button>
            </div>
            <div className="modal-body">
              {bulkLoading ? (
                <div className="inbox-empty-state"><div className="loading-spinner" /></div>
              ) : bulkRows.length === 0 ? (
                <div className="inbox-empty-state">
                  <div className="inbox-empty-state-text">발송 가능한 대화가 없습니다</div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {bulkRows.map(row => (
                    <label key={row.conversation_id} style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "12px",
                      padding: "12px",
                      background: row.selected ? "var(--primary-bg)" : "var(--bg)",
                      borderRadius: "var(--radius)",
                      cursor: "pointer",
                      border: row.selected ? "1px solid var(--primary)" : "1px solid var(--border)",
                    }}>
                      <input
                        type="checkbox"
                        checked={row.selected}
                        onChange={e => setBulkRows(prev => prev.map(r => r.conversation_id === row.conversation_id ? { ...r, selected: e.target.checked } : r))}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600 }}>{row.guest_name || "게스트"}</div>
                        {row.draft_content && (
                          <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
                            {row.draft_content.slice(0, 100)}...
                          </div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              )}
              {bulkError && <div style={{ color: "var(--danger)", marginTop: "12px" }}>{bulkError}</div>}
              {bulkResults && (
                <div style={{ marginTop: "16px" }}>
                  <div style={{ fontWeight: 600, marginBottom: "8px" }}>결과</div>
                  {bulkResults.map(r => (
                    <div key={r.conversation_id} style={{ fontSize: "13px", padding: "4px 0" }}>
                      <span className={`inbox-status-badge ${r.result === "sent" ? "ready" : "blocked"}`}>{r.result}</span>
                      <span style={{ marginLeft: "8px" }}>{r.airbnb_thread_id}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={() => setBulkOpen(false)} className="inbox-btn inbox-btn-secondary">닫기</button>
              <button onClick={runBulkSend} disabled={bulkSending || !bulkRows.some(r => r.selected)} className="inbox-btn inbox-btn-primary">
                {bulkSending ? "발송 중..." : `${bulkRows.filter(r => r.selected).length}개 발송`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Room Assignment Modal */}
      {showRoomAssignmentModal && detail?.conversation.airbnb_thread_id && (
        <RoomAssignmentModal
          threadId={detail.conversation.airbnb_thread_id}
          onClose={() => setShowRoomAssignmentModal(false)}
          onAssigned={async () => {
            if (detail) {
              const refreshed = await getConversationDetail(detail.conversation.id);
              setDetail(refreshed);
              setConversationDetail(detail.conversation.id, refreshed);
              syncDetailToList(detail.conversation.id, refreshed);
            }
            showToast({ type: "success", title: "객실이 배정되었습니다." });
          }}
        />
      )}
    </div>
  );
};
