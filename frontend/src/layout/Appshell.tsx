// src/layout/Appshell.tsx
import type { ReactNode } from "react";
import { MainNav } from "./MainNav";
import { TonoLogo } from "../components/branding/TonoLogo";

interface AppShellProps {
  children: ReactNode;
}

/**
 * ✅ 겹침 원인 해결:
 * 1) header가 fixed/absolute로 떠있거나(레이아웃 영역을 차지 안 함) main이 위로 끌려올라가면
 *    "OPERATION CONSOLE"과 페이지 타이틀이 같은 y축에 겹침.
 * 2) 타이틀 2줄(톤오퍼레이션/콘솔)이 line-height가 너무 작거나(leading 0) 같은 baseline에 겹침.
 *
 * 해결:
 * - header: sticky(레이아웃 흐름 유지 + 위에 고정)
 * - main: header 아래에서 시작하도록 일반 흐름 유지
 * - 텍스트: block + leading-tight + gap 지정
 */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col">
        {/* ✅ fixed/absolute 금지. sticky로 흐름 유지 + 겹침 방지 */}
        <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/80 backdrop-blur px-4 py-3 md:px-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <TonoLogo className="h-7 w-7 shrink-0" />

              {/* ✅ 2줄 텍스트 겹침 방지: block + leading + gap */}
              <div className="flex flex-col gap-0.5">
                <span className="block text-sm font-semibold tracking-wide leading-tight">
                  TONO OPERATION
                </span>
                <span className="block text-[10px] text-slate-400 leading-tight">
                  OPERATION CONSOLE
                </span>
              </div>
            </div>

            <div className="hidden md:block">
              <MainNav />
            </div>
          </div>
        </header>

        <div className="border-b border-slate-800 bg-slate-950/80 px-4 pb-3 pt-2 backdrop-blur md:hidden">
          <MainNav />
        </div>

        {/* ✅ main이 header 위로 올라가서 겹치지 않게: 일반 흐름 + min-h-0 */}
        <main className="flex-1 min-h-0 px-4 py-4 md:px-6 md:py-6">
          <div className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-800 bg-slate-950/60 p-4 md:p-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
