// src/components/layout/PageLayout.tsx
import React from "react";

interface PageLayoutProps {
  title: string;
  children: React.ReactNode;
  rightHeader?: React.ReactNode;
}

export const PageLayout: React.FC<PageLayoutProps> = ({
  title,
  children,
  rightHeader,
}) => {
  return (
    <div className="flex flex-col h-screen bg-slate-50">
      <header className="flex items-center justify-between px-6 py-4 border-b bg-white">
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        <div>{rightHeader}</div>
      </header>
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
};
