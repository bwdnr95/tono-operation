// src/layout/IntentBadge.tsx
// src/components/inbox/IntentBadge.tsx
import React from "react";

interface IntentBadgeProps {
  intent: string | null;
  fineIntent?: string | null;
}

export const IntentBadge: React.FC<IntentBadgeProps> = ({
  intent,
  fineIntent,
}) => {
  if (!intent) {
    return (
      <span className="inline-flex items-center rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">
        미분류
      </span>
    );
  }

  const label = fineIntent ? `${intent} / ${fineIntent}` : intent;

  return (
    <span className="inline-flex items-center rounded-full bg-slate-900 px-2 py-0.5 text-[11px] text-slate-200">
      {label}
    </span>
  );
};
