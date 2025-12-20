// src/components/conversations/ConversationList.tsx
import type { ConversationListItemDTO } from "../../types/conversations";
import { ConversationListItem } from "./ConversationListItem";

interface Props {
  items: ConversationListItemDTO[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ConversationList({ items, selectedId, onSelect }: Props) {
  if (!items.length) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <p className="text-sm text-dark-muted">표시할 대화가 없습니다</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      {items.map((item) => (
        <ConversationListItem
          key={item.id}
          item={item}
          selected={item.id === selectedId}
          onClick={() => onSelect(item.id)}
        />
      ))}
    </div>
  );
}
