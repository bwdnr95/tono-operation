// src/components/inbox/MessageListItem.tsx
import React from "react";

import { AutoReplyStatus } from "./AutoReplyStatus";
import type { MessageWithAutoReply } from "../../types/messages";
import { IntentBadge } from "../../layout/IntentBadge";

interface MessageListItemProps {
  item: MessageWithAutoReply;
  selected?: boolean;
  onClick?: () => void;
}

export const MessageListItem: React.FC<MessageListItemProps> = ({
  item,
  selected,
  onClick,
}) => {
  const auto = item.auto_reply ?? null;

  const otaLabel = item.ota || "UNKNOWN";
  const propertyCode = item.property_code || "N/A";
  const guestName = item.guest_name || null;
  const checkin = item.checkin_date;
  const checkout = item.checkout_date;

  const guestPreview =
    item.pure_guest_message ||
    item.subject ||
    item.ota_listing_name ||
    "(내용 없음)";

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "flex w-full flex-col gap-1 px-3 py-2.5 text-left transition-colors",
        selected
          ? "bg-slate-900/90"
          : "bg-transparent hover:bg-slate-900/70",
      ].join(" ")}
    >
      <div className="flex flex-col gap-1">
        {/* 🔹 1줄 메타 정보 + 시간 */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1 text-[11px] text-slate-400">
            <span className="font-mono text-[11px] text-slate-300">
              {propertyCode}
            </span>
            <span className="text-slate-600">·</span>
            <span className="uppercase">{otaLabel}</span>
            {guestName && (
              <>
                <span className="text-slate-600">·</span>
                <span>{guestName}</span>
              </>
            )}
            {checkin && (
              <>
                <span className="text-slate-600">·</span>
                <span>
                  {checkin}
                  {checkout ? ` ~ ${checkout}` : ""}
                </span>
              </>
            )}
          </div>

          <div className="shrink-0 text-[11px] text-slate-500">
            {new Date(item.received_at).toLocaleString("ko-KR")}
          </div>
        </div>

        {/* 🔹 제목 */}
        <div className="truncate text-sm font-medium text-slate-50">
          {item.subject || "(제목 없음)"}
        </div>

        {/* 🔹 본문 미리보기 */}
        <div className="truncate text-xs text-slate-400">
          {guestPreview}
        </div>

        {/* 🔹 Intent / AutoReply 상태 */}
        <div className="mt-1 flex items-center justify-between gap-2">
          <IntentBadge
            intent={auto?.intent || item.intent || null}
            fineIntent={auto?.fine_intent || item.fine_intent || null}
          />
          <AutoReplyStatus
            sent={!!auto?.sent}
            sendMode={auto?.send_mode ?? null}
          />
        </div>
      </div>
    </button>
  );
};
