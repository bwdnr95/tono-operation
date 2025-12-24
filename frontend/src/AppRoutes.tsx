// src/AppRoutes.tsx
import { Routes, Route } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage";
import { InboxPage } from "./pages/InboxPage";
import { StaffNotificationsPage } from "./pages/StaffNotificationsPage";
import { PropertiesPage } from "./pages/PropertiesPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/staff-notifications" element={<StaffNotificationsPage />} />
      <Route path="/properties" element={<PropertiesPage />} />
    </Routes>
  );
}
