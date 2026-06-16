"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { LogEvent, Server, Incident } from "@/lib/types";
import SystemLog from "@/components/SystemLog";
import InfraPanel from "@/components/InfraPanel";
import TriggerBar from "@/components/TriggerBar";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Page() {
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [servers, setServers] = useState<Server[]>([]);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [sseStatus, setSseStatus] = useState<"connecting" | "connected" | "error">(
    "connecting"
  );
  const [sysError, setSysError] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);

  const appendLog = useCallback((entry: LogEvent) => {
    setLogs((prev) => [...prev, entry]);
  }, []);

  useEffect(() => {
    const es = new EventSource(`${API_URL}/stream`);
    esRef.current = es;

    es.onopen = () => setSseStatus("connected");
    es.onerror = () => setSseStatus("error");

    // Named SSE events per data-contracts §7
    es.addEventListener("log", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        // payload may be the raw LogEvent or wrapped { type, data }
        const logEntry: LogEvent = payload.data ?? payload;
        appendLog(logEntry);
      } catch {
        // ignore malformed frames
      }
    });

    es.addEventListener("state", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const stateData = payload.data ?? payload;
        setServers(stateData.servers ?? []);
      } catch {
        // ignore malformed frames
      }
    });

    es.addEventListener("incident", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const incidentData: Incident = payload.data ?? payload;
        setIncident(incidentData);
      } catch {
        // ignore malformed frames
      }
    });

    // Some backends emit everything as a single default "message" event with a type field
    es.onmessage = (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const type: string = payload.type;
        const data = payload.data ?? payload;

        if (type === "log") {
          appendLog(data as LogEvent);
        } else if (type === "state") {
          setServers((data as { servers: Server[] }).servers ?? []);
        } else if (type === "incident") {
          setIncident(data as Incident);
        }
      } catch {
        // ignore
      }
    };

    return () => {
      es.close();
    };
  }, [appendLog]);

  const sseDot =
    sseStatus === "connected"
      ? "bg-green-500"
      : sseStatus === "error"
      ? "bg-red-500 animate-pulse"
      : "bg-yellow-500 animate-pulse";

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* ── Top bar ── */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-mono font-bold text-lg tracking-widest text-zinc-100">
            CALLSIGN
          </span>
          <span className="font-mono text-xs text-zinc-500 tracking-widest uppercase pt-0.5">
            AI Incident Response
          </span>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs">
          <span className={`w-2 h-2 rounded-full ${sseDot}`} />
          <span className="text-zinc-500 uppercase tracking-widest">
            {sseStatus === "connected"
              ? "Stream connected"
              : sseStatus === "error"
              ? "Stream unavailable"
              : "Connecting…"}
          </span>
        </div>
      </header>

      {/* ── System error banner ── */}
      {sysError && (
        <div className="px-6 py-2 bg-red-950/60 border-b border-red-800 font-mono text-xs text-red-400">
          {sysError}
          <button
            onClick={() => setSysError(null)}
            className="ml-4 text-red-600 hover:text-red-400"
          >
            [dismiss]
          </button>
        </div>
      )}

      {/* ── Incident script banner ── */}
      {incident?.status === "awaiting_approval" && incident.script && (
        <div className="px-6 py-3 bg-amber-950/40 border-b border-amber-800 font-mono text-sm text-amber-300">
          <span className="text-amber-600 text-xs tracking-widest uppercase mr-3">
            Voice Script
          </span>
          {incident.script}
        </div>
      )}

      {/* ── Main two-panel war room ── */}
      <main className="flex flex-1 overflow-hidden">
        {/* LEFT — System log */}
        <section className="flex-1 flex flex-col border-r border-zinc-800 overflow-hidden">
          <SystemLog logs={logs} />
        </section>

        {/* RIGHT — Infrastructure tiles */}
        <section className="w-80 flex flex-col overflow-hidden">
          <InfraPanel servers={servers} incident={incident} />
        </section>
      </main>

      {/* ── Bottom trigger / approval bar ── */}
      <TriggerBar
        apiUrl={API_URL}
        incident={incident}
        onError={(msg) => setSysError(msg)}
      />
    </div>
  );
}
