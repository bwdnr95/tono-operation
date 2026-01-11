// src/components/ui/Toast.tsx
/**
 * 전역 토스트 알림 시스템
 * - 체크마크 애니메이션 (success)
 * - 타입별 아이콘
 * - 슬라이드 인/아웃
 * - 구체적인 메시지
 */
import React, { createContext, useContext, useState, useCallback, useEffect } from "react";

// ============================================================
// Types
// ============================================================

type ToastType = "success" | "error" | "info" | "warning";

interface ToastData {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastContextType {
  showToast: (toast: Omit<ToastData, "id">) => void;
}

// ============================================================
// Context
// ============================================================

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}

// ============================================================
// Icons
// ============================================================

function SuccessIcon() {
  return (
    <svg className="toast-icon-svg toast-icon-success" viewBox="0 0 52 52" width="24" height="24">
      <circle className="toast-icon-circle" cx="26" cy="26" r="25" fill="none" />
      <path className="toast-icon-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg className="toast-icon-svg toast-icon-error" viewBox="0 0 52 52" width="24" height="24">
      <circle className="toast-icon-circle" cx="26" cy="26" r="25" fill="none" />
      <path className="toast-icon-x" fill="none" d="M16 16 36 36 M36 16 16 36" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg className="toast-icon-svg toast-icon-info" viewBox="0 0 52 52" width="24" height="24">
      <circle className="toast-icon-circle" cx="26" cy="26" r="25" fill="none" />
      <path className="toast-icon-info-mark" fill="none" d="M26 18 L26 18.5 M26 24 L26 36" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg className="toast-icon-svg toast-icon-warning" viewBox="0 0 52 52" width="24" height="24">
      <path className="toast-icon-triangle" fill="none" d="M26 8 L48 44 L4 44 Z" />
      <path className="toast-icon-exclaim" fill="none" d="M26 20 L26 32 M26 38 L26 38.5" />
    </svg>
  );
}

// ============================================================
// Toast Item
// ============================================================

function ToastItem({ toast, onClose }: { toast: ToastData; onClose: () => void }) {
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    const duration = toast.duration || (toast.type === "error" ? 5000 : 4000);
    const timer = setTimeout(() => {
      setIsExiting(true);
      setTimeout(onClose, 300); // 애니메이션 후 제거
    }, duration);
    return () => clearTimeout(timer);
  }, [toast, onClose]);

  const handleClose = () => {
    setIsExiting(true);
    setTimeout(onClose, 300);
  };

  const getIcon = () => {
    switch (toast.type) {
      case "success": return <SuccessIcon />;
      case "error": return <ErrorIcon />;
      case "info": return <InfoIcon />;
      case "warning": return <WarningIcon />;
    }
  };

  return (
    <div className={`toast toast-${toast.type} ${isExiting ? "toast-exit" : ""}`}>
      <div className="toast-icon">{getIcon()}</div>
      <div className="toast-content">
        <div className="toast-title">{toast.title}</div>
        {toast.message && <div className="toast-message">{toast.message}</div>}
      </div>
      <button className="toast-close" onClick={handleClose} aria-label="닫기">
        ×
      </button>
    </div>
  );
}

// ============================================================
// Provider
// ============================================================

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([]);

  const showToast = useCallback((toast: Omit<ToastData, "id">) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setToasts(prev => [...prev, { ...toast, id }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="toast-container">
        {toasts.map(toast => (
          <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// ============================================================
// Shorthand hooks
// ============================================================

export function useToastActions() {
  const { showToast } = useToast();

  return {
    success: (title: string, message?: string) => 
      showToast({ type: "success", title, message }),
    error: (title: string, message?: string) => 
      showToast({ type: "error", title, message, duration: 5000 }),
    info: (title: string, message?: string) => 
      showToast({ type: "info", title, message }),
    warning: (title: string, message?: string) => 
      showToast({ type: "warning", title, message }),
  };
}
