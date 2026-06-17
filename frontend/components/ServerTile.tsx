"use client";

import { Server, ServerStatus } from "@/lib/types";

interface Props {
  server: Server;
  isBlastRadius?: boolean;
}

type StatusConfig = {
  label: string;
  borderClass: string;
  labelClass: string;
  dotClass: string;
  bgClass: string;
  blink: boolean;
  flash: boolean;
};

// status → visual mapping per docs/frontend.md
const STATUS_CONFIG: Record<ServerStatus, StatusConfig> = {
  healthy: {
    label: "[ HEALTHY ]",
    borderClass: "border-green-900",
    labelClass: "text-green-700",
    dotClass: "bg-green-700",
    bgClass: "bg-zinc-900",
    blink: false,
    flash: false,
  },
  compromised: {
    label: "[COMPROMISED]",
    borderClass: "border-red-500",
    labelClass: "text-red-400",
    dotClass: "bg-red-500",
    bgClass: "bg-zinc-900",
    blink: true,
    flash: false,
  },
  degraded: {
    label: "[ DEGRADED ]",
    borderClass: "border-amber-500",
    labelClass: "text-amber-400",
    dotClass: "bg-red-500",
    bgClass: "bg-zinc-900",
    blink: true,   // blinking red/amber per spec
    flash: false,
  },
  isolated: {
    label: "[ ISOLATED ]",
    borderClass: "border-zinc-500",
    labelClass: "text-zinc-400",
    dotClass: "bg-zinc-500",
    bgClass: "bg-zinc-900",
    blink: false,
    flash: false,
  },
  rolled_back: {
    label: "[ROLLED BACK]",
    borderClass: "border-blue-500",
    labelClass: "text-blue-400",
    dotClass: "bg-blue-500",
    bgClass: "bg-zinc-900",
    blink: false,
    flash: false,
  },
  recovered: {
    label: "[ RECOVERED ]",
    borderClass: "border-green-400",
    labelClass: "text-green-400",
    dotClass: "bg-green-400",
    bgClass: "bg-green-950/20",
    blink: false,
    flash: true,   // solid green flash payoff moment
  },
};

export default function ServerTile({ server, isBlastRadius }: Props) {
  const cfg = STATUS_CONFIG[server.status] ?? STATUS_CONFIG.healthy;

  const isAffected = server.status !== "healthy";
  const showBlastBadge = isBlastRadius && !isAffected;

  return (
    <div
      data-testid={`server-tile-${server.id}`}
      className={[
        "border rounded font-mono p-3 transition-all duration-500",
        cfg.borderClass,
        cfg.bgClass,
        showBlastBadge ? "border-yellow-800 bg-yellow-950/30" : "",
        server.status === "compromised" || server.status === "degraded"
          ? "shadow-red-900/50 shadow-lg"
          : "",
        server.status === "isolated" ? "shadow-zinc-800/50 shadow-md" : "",
        server.status === "rolled_back" ? "shadow-blue-900/40 shadow-lg" : "",
        server.status === "recovered"
          ? "shadow-green-500/40 shadow-xl animate-[greenFlash_1.5s_ease-out]"
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="flex items-center justify-between gap-2">
        {/* server id + name */}
        <div>
          <div className="text-xs text-zinc-500 tracking-widest uppercase">
            {server.id}
          </div>
          <div className="text-sm text-zinc-200 font-semibold">{server.name}</div>
          <div className="text-xs text-zinc-500">{server.service}</div>
        </div>

        {/* status badge */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex items-center gap-1.5">
            <span
              className={[
                "w-2 h-2 rounded-full",
                cfg.dotClass,
                cfg.blink ? "animate-pulse" : "",
              ].join(" ")}
            />
            <span
              className={[
                "text-xs font-bold tracking-tight",
                cfg.labelClass,
                cfg.blink ? "animate-[blink_1s_step-end_infinite]" : "",
              ].join(" ")}
            >
              {cfg.label}
            </span>
          </div>
          {showBlastBadge && (
            <span className="text-[10px] text-yellow-600 tracking-widest">
              BLAST RADIUS
            </span>
          )}
        </div>
      </div>

      <div className="mt-2 text-[10px] text-zinc-600 font-mono truncate">
        {server.container}
      </div>
    </div>
  );
}
