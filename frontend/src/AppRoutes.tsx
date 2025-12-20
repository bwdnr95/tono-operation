// src/AppRoutes.tsx
import { Routes, Route } from "react-router-dom";
import { InboxPage } from "./pages/InboxPage";
import { StaffNotificationsPage } from "./pages/StaffNotificationsPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<InboxPage />} />
      <Route path="/staff-notifications" element={<StaffNotificationsPage />} />
    </Routes>
  );
}