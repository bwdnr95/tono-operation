// src/components/layout/PageLayout.tsx
import React from "react";

interface PageLayoutProps {
  title?: string;  // optional로 변경
  children: React.ReactNode;
  rightHeader?: React.ReactNode;
}

export const PageLayout: React.FC<PageLayoutProps> = ({
  title,
  children,
  rightHeader,
}) => {
  return (
    <div className="flex flex-col h-screen" style={{ background: "var(--bg)" }}>
      {title && (
        <header className="flex items-center justify-between px-6 py-4 border-b" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
          <h1 className="text-xl font-semibold" style={{ color: "var(--text)" }}>{title}</h1>
          <div>{rightHeader}</div>
        </header>
      )}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
};
