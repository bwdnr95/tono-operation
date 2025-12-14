// TonoLogo.tsx (최종 예시)
import type { ComponentProps } from "react";
import logo from "../../assets/tono-logo.png";

type TonoLogoProps = {
  compact?: boolean;
} & ComponentProps<"div">;

export function TonoLogo({
  compact = false,
  className = "",
  ...rest
}: TonoLogoProps) {
  return (
    <div
      className={`inline-flex items-center gap-3 ${className}`}
      {...rest}
    >
      <img
        src={logo}
        alt="TONO OPERATION"
        className={
          compact
            ? "block h-10 w-auto max-h-none"
            : "block h-16 w-auto max-h-none md:h-20"
        }
      />

      {!compact && (
        <div className="hidden flex-col leading-tight sm:flex">
          <span className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
            OPERATION CONSOLE
          </span>
        </div>
      )}
    </div>
  );
}
