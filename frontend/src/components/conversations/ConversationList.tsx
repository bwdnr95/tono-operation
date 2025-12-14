// src/components/conversations/ConversationList.tsx
import React from "react";
import type { ConversationListItemDTO } from "../../types/conversations";
import { ConversationListItem } from "./ConversationListItem";

export function ConversationList(props: {
  items: ConversationListItemDTO[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { items, selectedId, onSelect } = props;

  if (!items.length) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-xs text-slate-500">
        표시할 thread Conversation이 없습니다.
      </div>
    );
  }

  return (
    <div className="h-full divide-y divide-slate-900 overflow-y-auto">
      {items.map((it) => (
        <ConversationListItem
          key={it.id}
          item={it}
          selected={it.id === selectedId}
          onClick={() => onSelect(it.id)}
        />
      ))}
    </div>
  );
}
