"use client";

import { ExecutionMode } from "@/lib/types";

interface Props {
  mode: ExecutionMode;
}

export default function ModeBanner({ mode }: Props) {
  const isLive = mode === "real";

  return (
    <div
      className={[
        "flex items-center justify-center gap-3 px-6 py-1.5 font-mono text-xs tracking-widest uppercase shrink-0",
        isLive
          ? "bg-red-950/80 border-b border-red-700 text-red-300"
          : "bg-zinc-900/80 border-b border-zinc-700 text-zinc-400",
      ].join(" ")}
    >
      <span
        className={[
          "w-1.5 h-1.5 rounded-full",
          isLive ? "bg-red-400 animate-pulse" : "bg-zinc-500",
        ].join(" ")}
      />
      <span>
        EXECUTION_MODE:{" "}
        <span className={isLive ? "text-red-300 font-bold" : "text-zinc-300 font-bold"}>
          {isLive ? "LIVE" : "SIMULATED"}
        </span>
      </span>
      {isLive && (
        <span className="text-red-500 font-bold animate-pulse">
          — REAL ACTIONS WILL EXECUTE
        </span>
      )}
    </div>
  );
}
