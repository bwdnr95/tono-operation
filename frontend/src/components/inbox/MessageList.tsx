// src/components/inbox/MessageList.tsx
import React from "react";
import { MessageListItem } from "./MessageListItem";
import type { MessageWithAutoReply } from "../../types/messages";

interface MessageListProps {
  items: MessageWithAutoReply[];
  selectedId?: number | null;
  onSelect?: (messageId: number) => void;
}

export const MessageList: React.FC<MessageListProps> = ({
  items,
  selectedId,
  onSelect,
}) => {
  if (items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-xs text-slate-500">
        표시할 메시지가 없습니다.
      </div>
    );
  }

  return (
    <div className="h-full divide-y divide-slate-900 overflow-y-auto">
      {items.map((item) => (
        <MessageListItem
          key={item.id}
          item={item}
          selected={item.id === selectedId}
          onClick={() => onSelect?.(item.id)}
        />
      ))}
    </div>
  );
};
