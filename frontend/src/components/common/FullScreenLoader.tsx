// src/components/common/FullScreenLoader.tsx
import React from "react";
import { TonoLogo } from "../branding/TonoLogo";


export default function FullScreenLoader() {
  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-slate-950">
      {/* TONO 로고 */}
      <div className="animate-pulse opacity-80">
        <TonoLogo />
      </div>

      <div className="mt-6 text-sm text-slate-400">
        데이터를 불러오는 중입니다...
      </div>
    </div>
  );
}
