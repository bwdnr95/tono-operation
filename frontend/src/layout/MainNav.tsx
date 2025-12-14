// src/layout/MainNav.tsx
// src/components/layout/MainNav.tsx
import { NavLink } from "react-router-dom";

export function MainNav() {
  const baseClasses =
    "px-3 py-1.5 rounded-full text-xs md:text-sm transition-colors";

  const makeClass = (isActive: boolean) =>
    [
      baseClasses,
      isActive
        ? "bg-emerald-500 text-slate-950 shadow-sm shadow-emerald-500/40"
        : "bg-slate-900/40 text-slate-300 hover:bg-slate-800 hover:text-slate-50",
    ].join(" ");

  return (
    <nav className="flex flex-wrap items-center gap-2">
      <NavLink
        to="/"
        end
        className={({ isActive }) => makeClass(isActive)}
      >
        Inbox
      </NavLink>

      <NavLink
        to="/auto-replies"
        className={({ isActive }) => makeClass(isActive)}
      >
        Auto Reply 로그
      </NavLink>

      <NavLink
        to="/staff-notifications"
        className={({ isActive }) => makeClass(isActive)}
      >
        알림센터
      </NavLink>
    </nav>
  );
}
