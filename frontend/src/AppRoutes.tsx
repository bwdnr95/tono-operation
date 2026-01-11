// src/AppRoutes.tsx
import { Routes, Route } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage";
import { InboxPage } from "./pages/InboxPage";
import { StaffNotificationsPage } from "./pages/StaffNotificationsPage";
import { PropertiesPage } from "./pages/PropertiesPage";
import { PropertyGroupsPage } from "./pages/PropertyGroupsPage";
import BookingRequestsPage from "./pages/BookingRequestsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import CalendarPage from "./pages/CalendarPage";
import ReservationsPage from "./pages/ReservationsPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/reservations" element={<ReservationsPage />} />
      <Route path="/booking-requests" element={<BookingRequestsPage />} />
      <Route path="/staff-notifications" element={<StaffNotificationsPage />} />
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="/calendar" element={<CalendarPage />} />
      <Route path="/properties" element={<PropertiesPage />} />
      <Route path="/property-groups" element={<PropertyGroupsPage />} />
    </Routes>
  );
}
