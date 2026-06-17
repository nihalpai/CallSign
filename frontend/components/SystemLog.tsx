"use client";

import { useEffect, useRef } from "react";
import { LogEvent } from "@/lib/types";

interface Props {
  logs: LogEvent[];
}

// source → Tailwind color class. SYSTEM dim, AGENT cyan, REMEDIATION violet, SLACK green, VOICE amber.
const SOURCE_CLASS: Record<string, string> = {
  SYSTEM:      "text-zinc-500",
  AGENT:       "text-cyan-400",
  REMEDIATION: "text-violet-400",
  SLACK:       "text-green-400",
  VOICE:       "text-amber-400",
};

// Fixed-width label per source so columns stay aligned.
const SOURCE_LABEL: Record<string, string> = {
  SYSTEM:      "SYSTEM     ",
  AGENT:       "AGENT      ",
  REMEDIATION: "REMEDIATION",
  SLACK:       "SLACK      ",
  VOICE:       "VOICE      ",
};

function formatTs(ts: string): string {
  try {
    return new Date(ts).toISOString().slice(11, 19);
  } catch {
    return ts;
  }
}

export default function SystemLog({ logs }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="flex flex-col h-full">
      {/* panel header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-700 shrink-0">
        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
        <span className="text-xs font-mono text-zinc-400 tracking-widest uppercase">
          System Log
        </span>
        <span className="ml-auto text-[10px] font-mono text-zinc-600">
          {logs.length} events
        </span>
      </div>

      {/* log body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-0.5 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent">
        {logs.length === 0 && (
          <p className="text-zinc-600 font-mono text-sm">
            Waiting for events…
          </p>
        )}
        {logs.map((log, i) => (
          <div key={i} className="flex gap-3 items-start font-mono text-sm leading-relaxed">
            <span className="text-zinc-600 shrink-0 tabular-nums text-xs pt-0.5 select-none">
              {formatTs(log.ts)}
            </span>
            <span
              className={`shrink-0 text-xs font-bold pt-0.5 ${SOURCE_CLASS[log.source] ?? "text-zinc-300"}`}
              style={{ minWidth: "7.5rem" }}
            >
              [{SOURCE_LABEL[log.source] ?? log.source}]
            </span>
            <span className="text-zinc-200 break-words">{log.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
