// src/components/ui/Skeleton.tsx
/**
 * 스켈레톤 UI 컴포넌트
 * - 로딩 중 콘텐츠 플레이스홀더
 * - shimmer 애니메이션 적용
 */
import React from "react";

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
}

export function Skeleton({ width = "100%", height = "14px", borderRadius = "4px", style }: SkeletonProps) {
  return (
    <div
      className="skeleton"
      style={{
        width,
        height,
        borderRadius,
        ...style,
      }}
    />
  );
}

export function SkeletonText({ width = "100%", lines = 1 }: { width?: string | number; lines?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === lines - 1 && lines > 1 ? "70%" : width}
          height="14px"
        />
      ))}
    </div>
  );
}

export function SkeletonAvatar({ size = 40 }: { size?: number }) {
  return <Skeleton width={size} height={size} borderRadius="50%" />;
}

// 대화 목록 아이템 스켈레톤
export function SkeletonConversationItem() {
  return (
    <div className="conversation-item skeleton-item">
      <SkeletonAvatar size={40} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Skeleton width="30%" height="16px" />
          <Skeleton width="50px" height="18px" borderRadius="12px" />
        </div>
        <Skeleton width="60%" height="14px" />
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Skeleton width="60px" height="20px" borderRadius="12px" />
          <Skeleton width="40px" height="12px" />
        </div>
      </div>
    </div>
  );
}

// 대화 목록 스켈레톤 (여러 개)
export function SkeletonConversationList({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonConversationItem key={i} />
      ))}
    </>
  );
}

// 메시지 버블 스켈레톤
export function SkeletonMessageBubble({ direction = "incoming" }: { direction?: "incoming" | "outgoing" }) {
  const isIncoming = direction === "incoming";
  return (
    <div
      className={`message ${direction}`}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isIncoming ? "flex-start" : "flex-end",
      }}
    >
      <Skeleton
        width={isIncoming ? "65%" : "55%"}
        height="60px"
        borderRadius="12px"
      />
      <Skeleton width="60px" height="12px" style={{ marginTop: "4px" }} />
    </div>
  );
}

// 메시지 목록 스켈레톤
export function SkeletonMessageList() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "16px" }}>
      <SkeletonMessageBubble direction="incoming" />
      <SkeletonMessageBubble direction="outgoing" />
      <SkeletonMessageBubble direction="incoming" />
    </div>
  );
}

// 대시보드 카드 스켈레톤
export function SkeletonStatCard() {
  return (
    <div className="card skeleton-card" style={{ padding: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <Skeleton width="80px" height="14px" />
        <Skeleton width="24px" height="24px" borderRadius="50%" />
      </div>
      <Skeleton width="60%" height="32px" style={{ marginBottom: "8px" }} />
      <Skeleton width="100px" height="12px" />
    </div>
  );
}

// 대시보드 스켈레톤
export function SkeletonDashboard() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px" }}>
      <SkeletonStatCard />
      <SkeletonStatCard />
      <SkeletonStatCard />
      <SkeletonStatCard />
    </div>
  );
}

// 상세 패널 헤더 스켈레톤
export function SkeletonDetailHeader() {
  return (
    <div className="card-header" style={{ borderBottom: "1px solid var(--border)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <SkeletonAvatar size={36} />
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <Skeleton width="120px" height="16px" />
          <Skeleton width="80px" height="12px" />
        </div>
      </div>
      <div style={{ display: "flex", gap: "8px" }}>
        <Skeleton width="60px" height="24px" borderRadius="12px" />
        <Skeleton width="50px" height="24px" borderRadius="12px" />
      </div>
    </div>
  );
}

// 전체 대화 상세 스켈레톤
export function SkeletonConversationDetail() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SkeletonDetailHeader />
      <div style={{ flex: 1, background: "var(--bg)" }}>
        <SkeletonMessageList />
      </div>
      <div className="composer" style={{ padding: "16px" }}>
        <Skeleton width="100%" height="80px" borderRadius="8px" />
        <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
          <Skeleton width="100px" height="36px" borderRadius="6px" />
          <Skeleton width="80px" height="36px" borderRadius="6px" />
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Analytics 스켈레톤
// ============================================================

// Analytics Stat Card 스켈레톤
export function SkeletonAnalyticsStatCard() {
  return (
    <div className="stat-card skeleton-card">
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
        <Skeleton width="24px" height="24px" borderRadius="4px" />
        <Skeleton width="60px" height="14px" />
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginBottom: "8px" }}>
        <Skeleton width="80px" height="32px" />
        <Skeleton width="20px" height="14px" />
      </div>
      <Skeleton width="100px" height="12px" />
    </div>
  );
}

// Analytics Stat Grid 스켈레톤
export function SkeletonAnalyticsStatGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="stat-grid">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonAnalyticsStatCard key={i} />
      ))}
    </div>
  );
}

// Analytics 차트 스켈레톤
export function SkeletonAnalyticsChart() {
  return (
    <div className="card" style={{ padding: "16px" }}>
      <Skeleton width="150px" height="16px" style={{ marginBottom: "16px" }} />
      <div style={{ display: "flex", alignItems: "flex-end", gap: "12px", height: "120px" }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
            <Skeleton 
              width="100%" 
              height={`${30 + Math.random() * 70}%`} 
              borderRadius="4px 4px 0 0" 
            />
            <Skeleton width="24px" height="12px" />
          </div>
        ))}
      </div>
    </div>
  );
}

// Analytics 테이블 스켈레톤
export function SkeletonAnalyticsTable({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <table className="table">
        <thead>
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i}>
                <Skeleton width={i === 0 ? "100px" : "60px"} height="14px" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIdx) => (
            <tr key={rowIdx}>
              {Array.from({ length: cols }).map((_, colIdx) => (
                <td key={colIdx}>
                  {colIdx === 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                      <Skeleton width="100px" height="14px" />
                      <Skeleton width="60px" height="12px" />
                    </div>
                  ) : (
                    <Skeleton width="50px" height="14px" style={{ marginLeft: "auto" }} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Analytics 전체 페이지 스켈레톤
export function SkeletonAnalyticsPage() {
  return (
    <div style={{ padding: "24px 32px" }}>
      {/* 기간 정보 */}
      <Skeleton width="150px" height="14px" style={{ marginBottom: "16px" }} />
      
      {/* 운영 지표 */}
      <div style={{ marginBottom: "24px" }}>
        <Skeleton width="100px" height="18px" style={{ marginBottom: "12px" }} />
        <SkeletonAnalyticsStatGrid count={4} />
      </div>
      
      {/* 수익 지표 */}
      <div style={{ marginBottom: "24px" }}>
        <Skeleton width="100px" height="18px" style={{ marginBottom: "12px" }} />
        <SkeletonAnalyticsStatGrid count={3} />
      </div>
      
      {/* 월별 트렌드 */}
      <div style={{ marginBottom: "24px" }}>
        <Skeleton width="100px" height="18px" style={{ marginBottom: "12px" }} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
          <SkeletonAnalyticsChart />
          <SkeletonAnalyticsChart />
        </div>
      </div>
      
      {/* 숙소별 비교 */}
      <div>
        <Skeleton width="100px" height="18px" style={{ marginBottom: "12px" }} />
        <SkeletonAnalyticsTable rows={4} cols={6} />
      </div>
    </div>
  );
}
