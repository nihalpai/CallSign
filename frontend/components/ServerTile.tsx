"use client";

import { Server, ServerStatus } from "@/lib/types";

interface Props {
  server: Server;
  isBlastRadius?: boolean;
}

const STATUS_CONFIG: Record<
  ServerStatus,
  { label: string; borderClass: string; labelClass: string; dotClass: string; pulse: boolean }
> = {
  healthy: {
    label: "[ HEALTHY ]",
    borderClass: "border-green-900",
    labelClass: "text-green-700",
    dotClass: "bg-green-700",
    pulse: false,
  },
  compromised: {
    label: "[COMPROMISED]",
    borderClass: "border-red-500",
    labelClass: "text-red-400",
    dotClass: "bg-red-500",
    pulse: true,
  },
  isolated: {
    label: "[ ISOLATED ]",
    borderClass: "border-green-400",
    labelClass: "text-green-400",
    dotClass: "bg-green-400",
    pulse: false,
  },
};

export default function ServerTile({ server, isBlastRadius }: Props) {
  const cfg = STATUS_CONFIG[server.status];

  return (
    <div
      className={[
        "border rounded font-mono p-3 transition-all duration-500",
        cfg.borderClass,
        isBlastRadius && server.status === "healthy"
          ? "border-yellow-800 bg-yellow-950/30"
          : "bg-zinc-900",
        server.status === "compromised" ? "shadow-red-900/50 shadow-lg" : "",
        server.status === "isolated" ? "shadow-green-900/40 shadow-lg" : "",
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
                cfg.pulse ? "animate-pulse" : "",
              ].join(" ")}
            />
            <span
              className={[
                "text-xs font-bold tracking-tight",
                cfg.labelClass,
                cfg.pulse ? "animate-[blink_1s_step-end_infinite]" : "",
              ].join(" ")}
            >
              {cfg.label}
            </span>
          </div>
          {isBlastRadius && server.status === "healthy" && (
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
