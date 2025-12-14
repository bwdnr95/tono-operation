// src/App.tsx
import { BrowserRouter } from "react-router-dom";

import { AppRoutes } from "./AppRoutes";
import { AppShell } from "./layout/Appshell";

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <AppRoutes />
      </AppShell>
    </BrowserRouter>
  );
}
