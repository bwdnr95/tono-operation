// src/components/layout/PageLayout.tsx
import React from "react";

interface PageLayoutProps {
  title?: string;
  children: React.ReactNode;
  rightHeader?: React.ReactNode;
}

export const PageLayout: React.FC<PageLayoutProps> = ({
  title,
  children,
  rightHeader,
}) => {
  return (
    <div 
      className="flex flex-col h-screen" 
      style={{ background: '#08080c' }}
    >
      {title && (
        <header 
          className="flex items-center justify-between px-6 py-4"
          style={{ 
            background: '#0f0f14', 
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)' 
          }}
        >
          <h1 
            className="text-xl font-semibold" 
            style={{ color: '#ffffff' }}
          >
            {title}
          </h1>
          <div>{rightHeader}</div>
        </header>
      )}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
};
