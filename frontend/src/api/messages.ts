// src/api/messages.ts

import { api } from "./client";
import type {
  MessageListItem,
  MessageDetail,
  SuggestedReply,
  MessageIntent,
} from "../types/intents";

export const messagesApi = {
  list: (params?: { limit?: number; only_actionable?: boolean }) => {
    const limit = params?.limit ?? 50;
    const only = params?.only_actionable ?? true;
    const qs = `?limit=${limit}&only_actionable=${only ? "true" : "false"}`;
    return api.get<MessageListItem[]>(`/messages${qs}`);
  },

  detail: (id: number) =>
    api.get<MessageDetail>(`/messages/${id}`),

  suggestedReply: (id: number) =>
    api.get<SuggestedReply>(`/messages/${id}/suggested-reply`),

  createIntentLabel: (id: number, intent: MessageIntent) =>
    api.post(`/messages/${id}/intent-label`, { intent }),
};
