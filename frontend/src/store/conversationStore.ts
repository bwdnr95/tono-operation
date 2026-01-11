// src/store/conversationStore.ts
/**
 * Conversation Store - v4
 * 
 * 변경사항 (v4):
 * - Detail 캐시에 timestamp 추가 → stale 데이터 감지
 * - syncDetailToList: detail 변경 시 list item도 동기화
 * - invalidateDetail: 특정 detail 캐시 무효화
 * - isDetailStale: 캐시 유효성 체크 (기본 30초)
 * 
 * 목적:
 * 1. 최초 1회만 API 호출 → 전체 데이터 캐싱
 * 2. 탭 전환(안읽음/처리완료/전체)은 Store 필터링만 (API 호출 없음)
 * 3. 수정 시 로컬 즉시 반영 + API 호출
 * 4. Detail/List 동기화 보장
 */
import { create } from "zustand";
import type {
  ConversationListItemDTO,
  ConversationDetailDTO,
} from "../types/conversations";

// Detail 캐시 엔트리 (timestamp 포함)
interface CachedDetail {
  data: ConversationDetailDTO;
  cachedAt: number; // Date.now()
}

// 캐시 유효 시간 (ms)
const DETAIL_CACHE_TTL = 30 * 1000; // 30초

interface ConversationStore {
  // ===== 전체 데이터 캐시 =====
  allConversations: ConversationListItemDTO[];
  conversationDetails: Record<string, CachedDetail>;
  
  // ===== 필터 상태 =====
  isReadFilter: boolean | null; // false=안읽음, true=읽음, null=전체
  statusFilter: string;
  safetyFilter: string;
  threadIdFilter: string;
  sendActionFilter: string; // "" | "auto_sent" | "send" | "bulk_send"
  updatedSince: string;
  
  // ===== 선택 상태 =====
  selectedId: string | null;
  
  // ===== 로딩/에러 =====
  isInitialized: boolean;
  listLoading: boolean;
  detailLoading: boolean;
  error: string | null;
  
  // ===== Actions =====
  setAllConversations: (items: ConversationListItemDTO[]) => void;
  appendConversations: (items: ConversationListItemDTO[]) => void;
  updateConversationInList: (id: string, updates: Partial<ConversationListItemDTO>) => void;
  
  setConversationDetail: (id: string, detail: ConversationDetailDTO) => void;
  clearConversationDetail: (id: string) => void;
  clearAllConversationDetails: () => void;
  invalidateDetail: (id: string) => void; // 캐시 무효화 (다음 접근 시 재fetch)
  
  // Detail → List 동기화 (status, is_read, updated_at 등)
  syncDetailToList: (id: string, detail: ConversationDetailDTO) => void;
  
  setIsReadFilter: (v: boolean | null) => void;
  setStatusFilter: (v: string) => void;
  setSafetyFilter: (v: string) => void;
  setThreadIdFilter: (v: string) => void;
  setSendActionFilter: (v: string) => void;
  setUpdatedSince: (v: string) => void;
  
  setSelectedId: (id: string | null) => void;
  setInitialized: (v: boolean) => void;
  setListLoading: (v: boolean) => void;
  setDetailLoading: (v: boolean) => void;
  setError: (v: string | null) => void;
  
  // ===== 읽음 처리 (로컬 즉시 반영) =====
  markAsRead: (id: string) => void;
  
  // ===== Computed =====
  getFilteredConversations: () => ConversationListItemDTO[];
  getSelectedDetail: () => ConversationDetailDTO | null;
  getCachedDetail: (id: string) => ConversationDetailDTO | null;
  isDetailStale: (id: string) => boolean; // 캐시가 stale인지 체크
  
  // ===== Reset =====
  resetStore: () => void;
}

function isoNowMinusHours(h: number) {
  return new Date(Date.now() - h * 60 * 60 * 1000).toISOString();
}

const initialState = {
  allConversations: [] as ConversationListItemDTO[],
  conversationDetails: {} as Record<string, CachedDetail>,
  isReadFilter: false as boolean | null,
  statusFilter: "",
  safetyFilter: "",
  threadIdFilter: "",
  sendActionFilter: "",
  updatedSince: isoNowMinusHours(48),
  selectedId: null as string | null,
  isInitialized: false,
  listLoading: false,
  detailLoading: false,
  error: null as string | null,
};

export const useConversationStore = create<ConversationStore>((set, get) => ({
  ...initialState,
  
  // ===== Actions =====
  setAllConversations: (items) => set({ 
    allConversations: items,
    isInitialized: true,
  }),
  
  appendConversations: (items) => set((state) => {
    const existingIds = new Set(state.allConversations.map(c => c.id));
    const newItems = items.filter(item => !existingIds.has(item.id));
    return { allConversations: [...state.allConversations, ...newItems] };
  }),
  
  updateConversationInList: (id, updates) => set((state) => ({
    allConversations: state.allConversations.map(c => 
      c.id === id ? { ...c, ...updates } : c
    ),
  })),
  
  // Detail 캐시 설정 (timestamp 포함)
  setConversationDetail: (id, detail) => set((state) => ({
    conversationDetails: { 
      ...state.conversationDetails, 
      [id]: { data: detail, cachedAt: Date.now() } 
    },
  })),
  
  clearConversationDetail: (id) => set((state) => {
    const { [id]: _, ...rest } = state.conversationDetails;
    return { conversationDetails: rest };
  }),
  
  clearAllConversationDetails: () => set({ conversationDetails: {} }),
  
  // 캐시 무효화 (timestamp를 0으로 설정 → 다음 접근 시 stale 판정)
  invalidateDetail: (id) => set((state) => {
    const cached = state.conversationDetails[id];
    if (!cached) return state;
    return {
      conversationDetails: {
        ...state.conversationDetails,
        [id]: { ...cached, cachedAt: 0 },
      },
    };
  }),
  
  // Detail 변경 후 List item도 동기화
  syncDetailToList: (id, detail) => set((state) => ({
    allConversations: state.allConversations.map(c => {
      if (c.id !== id) return c;
      // Detail의 conversation 데이터로 list item 업데이트
      const conv = detail.conversation;
      return {
        ...c,
        status: conv.status,
        safety_status: conv.safety_status,
        is_read: conv.is_read,
        updated_at: conv.updated_at,
        property_code: conv.property_code,
        group_code: conv.group_code,
        guest_name: conv.guest_name,
        checkin_date: conv.checkin_date,
        checkout_date: conv.checkout_date,
        reservation_status: conv.reservation_status,
        last_send_action: conv.last_send_action,
      };
    }),
  })),
  
  setIsReadFilter: (v) => set({ isReadFilter: v }),
  setStatusFilter: (v) => set({ statusFilter: v }),
  setSafetyFilter: (v) => set({ safetyFilter: v }),
  setThreadIdFilter: (v) => set({ threadIdFilter: v }),
  setSendActionFilter: (v) => set({ sendActionFilter: v }),
  setUpdatedSince: (v) => set({ updatedSince: v }),
  
  setSelectedId: (id) => set({ selectedId: id }),
  setInitialized: (v) => set({ isInitialized: v }),
  setListLoading: (v) => set({ listLoading: v }),
  setDetailLoading: (v) => set({ detailLoading: v }),
  setError: (v) => set({ error: v }),
  
  // ===== 읽음 처리 =====
  markAsRead: (id) => set((state) => ({
    allConversations: state.allConversations.map(c =>
      c.id === id ? { ...c, is_read: true } : c
    ),
  })),
  
  // ===== 필터링 (API 호출 없음!) =====
  getFilteredConversations: () => {
    const state = get();
    let filtered = [...state.allConversations];
    
    // is_read 필터 (탭)
    if (state.isReadFilter !== null) {
      filtered = filtered.filter(c => c.is_read === state.isReadFilter);
    }
    
    // status 필터
    if (state.statusFilter) {
      filtered = filtered.filter(c => c.status === state.statusFilter);
    }
    
    // safety 필터
    if (state.safetyFilter) {
      filtered = filtered.filter(c => c.safety_status === state.safetyFilter);
    }
    
    // sendAction 필터 (auto_sent, send, bulk_send)
    if (state.sendActionFilter) {
      filtered = filtered.filter(c => c.last_send_action === state.sendActionFilter);
    }
    
    // thread_id / guest_name / property_code 필터 (부분 일치)
    if (state.threadIdFilter) {
      const q = state.threadIdFilter.toLowerCase();
      filtered = filtered.filter(c => 
        c.airbnb_thread_id.toLowerCase().includes(q) ||
        (c.guest_name && c.guest_name.toLowerCase().includes(q)) ||
        (c.property_code && c.property_code.toLowerCase().includes(q))
      );
    }
    
    // 최신순 정렬
    filtered.sort((a, b) => 
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
    
    return filtered;
  },
  
  getSelectedDetail: () => {
    const state = get();
    if (!state.selectedId) return null;
    const cached = state.conversationDetails[state.selectedId];
    return cached?.data || null;
  },
  
  // 캐시된 detail 가져오기 (stale 여부 상관없이)
  getCachedDetail: (id) => {
    const state = get();
    const cached = state.conversationDetails[id];
    return cached?.data || null;
  },
  
  // 캐시가 stale인지 체크 (TTL 초과 또는 무효화됨)
  isDetailStale: (id) => {
    const state = get();
    const cached = state.conversationDetails[id];
    if (!cached) return true; // 캐시 없음 = stale
    if (cached.cachedAt === 0) return true; // 명시적 무효화
    return Date.now() - cached.cachedAt > DETAIL_CACHE_TTL;
  },
  
  resetStore: () => set(initialState),
}));
