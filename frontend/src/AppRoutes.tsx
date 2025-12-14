// src/AppRoutes.tsx
import { Routes, Route } from "react-router-dom";
import { InboxPage } from "./pages/InboxPage";

import { StaffNotificationsPage } from "./pages/StaffNotificationsPage"; // ✅ 추가
import AutoReplyLogsPage from "./pages/AutoReplyLogsPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<InboxPage />} />
      <Route path="/auto-replies" element={<AutoReplyLogsPage />} />
      <Route
        path="/staff-notifications"
        element={<StaffNotificationsPage />} // ✅ 추가
      />
    </Routes>
  );
}
