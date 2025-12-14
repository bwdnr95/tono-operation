// src/components/ui/LoadingOverlay.tsx
import { TonoLogo } from "../branding/TonoLogo";

interface LoadingOverlayProps {
  message?: string;
  fullscreen?: boolean;
}

export function LoadingOverlay({
  message,
  fullscreen = false,
}: LoadingOverlayProps) {
  const positionClass = fullscreen ? "fixed inset-0" : "absolute inset-0";

  return (
    <div
      className={`${positionClass} z-40 flex items-center justify-center bg-slate-950/85`}
    >
      {/* 워터마크 TONO */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.045]">
        <div className="select-none text-7xl font-black tracking-[0.4em] text-slate-100 md:text-8xl">
          TONO
        </div>
      </div>

      {/* 중앙 로딩 영역 */}
      <div className="relative flex flex-col items-center gap-5">
        <TonoLogo />

        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 rounded-full border-2 border-slate-700 border-t-emerald-400 animate-spin" />
          <p className="text-xs text-slate-400">
            {message ?? "TONO OPERATION 데이터를 불러오는 중입니다..."}
          </p>
        </div>
      </div>
    </div>
  );
}
