// src/components/inbox/AutoReplyStatus.tsx
import React from "react";

interface AutoReplyStatusProps {
  sent: boolean;
  failureReason?: string | null;
  sendMode?: string | null;
}

export const AutoReplyStatus: React.FC<AutoReplyStatusProps> = ({
  sent,
  failureReason,
  sendMode,
}) => {
  if (failureReason) {
    return (
      <div className="inline-flex items-center gap-1 text-xs text-red-600">
        <span className="h-2 w-2 rounded-full bg-red-500" />
        실패 ({failureReason})
      </div>
    );
  }

  if (sent) {
    return (
      <div className="inline-flex items-center gap-1 text-xs text-emerald-700">
        <span className="h-2 w-2 rounded-full bg-emerald-500" />
        전송완료 {sendMode ? `(${sendMode})` : null}
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-1 text-xs text-amber-600">
      <span className="h-2 w-2 rounded-full bg-amber-400" />
      미전송
    </div>
  );
};
