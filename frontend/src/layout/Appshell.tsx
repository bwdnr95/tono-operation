// src/layout/Appshell.tsx
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

interface AppShellProps {
  children: ReactNode;
}

const navItems = [
  { to: "/", label: "대시보드", icon: "📊" },
  { to: "/inbox", label: "Inbox", icon: "📬" },
  { to: "/staff-notifications", label: "Staff Alerts", icon: "🔔" },
  { to: "/properties", label: "숙소 관리", icon: "🏠" },
];

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">T</div>
            <span className="sidebar-logo-text">TONO</span>
          </div>
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
    </div>
  );
}
