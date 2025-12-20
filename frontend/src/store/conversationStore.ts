// src/store/conversationStore.ts
/**
 * Conversation Store - v3
 * 
 * 목적:
 * 1. 최초 1회만 API 호출 → 전체 데이터 캐싱
 * 2. 탭 전환(안읽음/처리완료/전체)은 Store 필터링만 (API 호출 없음)
 * 3. 수정 시 로컬 즉시 반영 + API 호출
 */
import { create } from "zustand";
import type {
  ConversationListItemDTO,
  ConversationDetailDTO,
} from "../types/conversations";

interface ConversationStore {
  // ===== 전체 데이터 캐시 =====
  allConversations: ConversationListItemDTO[];
  conversationDetails: Record<string, ConversationDetailDTO>;
  
  // ===== 필터 상태 =====
  isReadFilter: boolean | null; // false=안읽음, true=읽음, null=전체
  statusFilter: string;
  safetyFilter: string;
  threadIdFilter: string;
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
  
  setIsReadFilter: (v: boolean | null) => void;
  setStatusFilter: (v: string) => void;
  setSafetyFilter: (v: string) => void;
  setThreadIdFilter: (v: string) => void;
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
  
  // ===== Reset =====
  resetStore: () => void;
}

function isoNowMinusHours(h: number) {
  return new Date(Date.now() - h * 60 * 60 * 1000).toISOString();
}

const initialState = {
  allConversations: [],
  conversationDetails: {},
  isReadFilter: false as boolean | null,
  statusFilter: "",
  safetyFilter: "",
  threadIdFilter: "",
  updatedSince: isoNowMinusHours(48),
  selectedId: null,
  isInitialized: false,
  listLoading: false,
  detailLoading: false,
  error: null,
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
  
  setConversationDetail: (id, detail) => set((state) => ({
    conversationDetails: { ...state.conversationDetails, [id]: detail },
  })),
  
  clearConversationDetail: (id) => set((state) => {
    const { [id]: _, ...rest } = state.conversationDetails;
    return { conversationDetails: rest };
  }),
  
  setIsReadFilter: (v) => set({ isReadFilter: v }),
  setStatusFilter: (v) => set({ statusFilter: v }),
  setSafetyFilter: (v) => set({ safetyFilter: v }),
  setThreadIdFilter: (v) => set({ threadIdFilter: v }),
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
    
    // thread_id 필터 (부분 일치)
    if (state.threadIdFilter) {
      filtered = filtered.filter(c => 
        c.airbnb_thread_id.toLowerCase().includes(state.threadIdFilter.toLowerCase())
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
    return state.conversationDetails[state.selectedId] || null;
  },
  
  resetStore: () => set(initialState),
}));
