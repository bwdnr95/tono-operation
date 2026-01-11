// src/layout/Appshell.tsx
import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { NotificationBell } from "../components/notifications/NotificationBell";
import { useTheme } from "../hooks/useTheme";
import tonoLogo from "../assets/tono-logo-horizontal.png";

interface AppShellProps {
  children: ReactNode;
}

const navItems = [
  { to: "/", label: "대시보드", icon: "🏠" },
  { to: "/inbox", label: "Inbox", icon: "📬" },
  { to: "/reservations", label: "예약 관리", icon: "📋" },
  { to: "/booking-requests", label: "예약 요청", icon: "📩" },
  { to: "/staff-notifications", label: "Staff Alerts", icon: "🔔" },
  { to: "/calendar", label: "달력", icon: "📅" },
  { to: "/analytics", label: "Analytics", icon: "📊" },
  { to: "/properties", label: "숙소 관리", icon: "🏡" },
  { to: "/property-groups", label: "숙소 그룹", icon: "📁" },
];

// 모바일 주요 메뉴 (하단 네비게이션용)
const mobileNavItems = [
  { to: "/inbox", label: "Inbox", icon: "📬" },
  { to: "/calendar", label: "달력", icon: "📅" },
  { to: "/", label: "홈", icon: "🏠" },
  { to: "/reservations", label: "예약", icon: "📋" },
];

export function AppShell({ children }: AppShellProps) {
  const { isDark, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  // 페이지 이동 시 사이드바 닫기
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // 사이드바 열렸을 때 스크롤 방지
  useEffect(() => {
    if (sidebarOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [sidebarOpen]);

  return (
    <div className="app-layout">
      {/* Mobile Header */}
      <header className="mobile-header">
        <button
          className="mobile-menu-btn"
          onClick={() => setSidebarOpen(true)}
          aria-label="메뉴 열기"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div className="mobile-header-logo">
          <img src={tonoLogo} alt="TONO" className="mobile-logo-img" />
        </div>
        <NotificationBell />
      </header>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div 
          className="mobile-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div className="sidebar-logo">
            <img src={tonoLogo} alt="TONO OPERATION" className="sidebar-logo-img" />
          </div>
          {/* Desktop: Notification Bell */}
          <div className="desktop-only">
            <NotificationBell />
          </div>
          {/* Mobile: Close Button */}
          <button 
            className="mobile-close-btn mobile-only"
            onClick={() => setSidebarOpen(false)}
            aria-label="메뉴 닫기"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? "active" : ""}`
              }
            >
              <span className="sidebar-link-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        
        {/* Sidebar Footer */}
        <div style={{ padding: "16px 20px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="theme-toggle"
            title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              gap: "12px",
              padding: "10px 12px",
              marginBottom: "12px",
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "var(--radius)",
              cursor: "pointer",
              color: "var(--text-sidebar)",
              fontSize: "13px",
              transition: "all 0.15s ease",
            }}
          >
            <span style={{ fontSize: "16px" }}>{isDark ? "🌙" : "☀️"}</span>
            <span>{isDark ? "다크 모드" : "라이트 모드"}</span>
            <span style={{ 
              marginLeft: "auto", 
              fontSize: "10px", 
              opacity: 0.6,
              padding: "2px 6px",
              background: "rgba(255,255,255,0.1)",
              borderRadius: "4px",
            }}>
              {isDark ? "ON" : "OFF"}
            </span>
          </button>
          
          <div style={{ fontSize: "11px", color: "var(--text-sidebar)" }}>
            TONO OPERATION
          </div>
          <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "4px" }}>
            v1.0.0 MVP
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {children}
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="mobile-bottom-nav">
        {mobileNavItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `mobile-nav-item ${isActive ? "active" : ""}`
            }
          >
            <span className="mobile-nav-icon">{item.icon}</span>
            <span className="mobile-nav-label">{item.label}</span>
          </NavLink>
        ))}
        <button 
          className="mobile-nav-item"
          onClick={() => setSidebarOpen(true)}
        >
          <span className="mobile-nav-icon">☰</span>
          <span className="mobile-nav-label">더보기</span>
        </button>
      </nav>
    </div>
  );
}
