// src/store/previewStore.ts
import { create } from "zustand";
import type {
  DraftReplyDTO,
  SendPreviewDTO,
  BulkSendPreviewResponseDTO,
  BulkSendSendResponseDTO,
} from "../types/conversations";

type ConversationId = string;

interface PreviewStore {
  draftsByConversation: Record<ConversationId, DraftReplyDTO | null>;
  setDraft: (conversationId: ConversationId, draft: DraftReplyDTO | null) => void;
  clearDraft: (conversationId: ConversationId) => void;

  sendPreviewByConversation: Record<ConversationId, SendPreviewDTO | null>;
  setSendPreview: (conversationId: ConversationId, preview: SendPreviewDTO | null) => void;
  clearSendPreview: (conversationId: ConversationId) => void;

  bulkPreview: BulkSendPreviewResponseDTO | null;
  setBulkPreview: (v: BulkSendPreviewResponseDTO | null) => void;

  bulkSendResult: BulkSendSendResponseDTO | null;
  setBulkSendResult: (v: BulkSendSendResponseDTO | null) => void;

  resetAll: () => void;
}

export const usePreviewStore = create<PreviewStore>((set) => ({
  draftsByConversation: {},
  setDraft: (conversationId, draft) =>
    set((prev) => ({
      draftsByConversation: { ...prev.draftsByConversation, [conversationId]: draft },
    })),
  clearDraft: (conversationId) =>
    set((prev) => {
      const next = { ...prev.draftsByConversation };
      delete next[conversationId];
      return { draftsByConversation: next };
    }),

  sendPreviewByConversation: {},
  setSendPreview: (conversationId, preview) =>
    set((prev) => ({
      sendPreviewByConversation: { ...prev.sendPreviewByConversation, [conversationId]: preview },
    })),
  clearSendPreview: (conversationId) =>
    set((prev) => {
      const next = { ...prev.sendPreviewByConversation };
      delete next[conversationId];
      return { sendPreviewByConversation: next };
    }),

  bulkPreview: null,
  setBulkPreview: (v) => set({ bulkPreview: v }),

  bulkSendResult: null,
  setBulkSendResult: (v) => set({ bulkSendResult: v }),

  resetAll: () =>
    set({
      draftsByConversation: {},
      sendPreviewByConversation: {},
      bulkPreview: null,
      bulkSendResult: null,
    }),
}));
