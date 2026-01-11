// src/App.tsx
import { BrowserRouter } from "react-router-dom";

import { AppRoutes } from "./AppRoutes";
import { AppShell } from "./layout/Appshell";
import { ToastProvider } from "./components/ui/Toast";

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppShell>
          <AppRoutes />
        </AppShell>
      </ToastProvider>
    </BrowserRouter>
  );
}
