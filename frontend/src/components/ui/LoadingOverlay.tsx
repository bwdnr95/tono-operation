// src/components/ui/LoadingOverlay.tsx
interface LoadingOverlayProps {
  message?: string;
}

export function LoadingOverlay({ message }: LoadingOverlayProps) {
  return (
    <div className="loading-overlay">
      <div className="card" style={{ padding: "32px 48px", textAlign: "center" }}>
        <div className="loading-spinner" style={{ margin: "0 auto 16px" }} />
        <p style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
          {message ?? "로딩 중..."}
        </p>
      </div>
    </div>
  );
}
