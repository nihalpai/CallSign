"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { LogEvent, Server, Incident } from "@/lib/types";
import SystemLog from "@/components/SystemLog";
import InfraPanel from "@/components/InfraPanel";
import TriggerBar from "@/components/TriggerBar";
import ModeBanner from "@/components/ModeBanner";
import IncidentDetail from "@/components/IncidentDetail";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
    es.onerror = (e) => {
      setSseStatus("error");
      console.error("[SSE] EventSource error", e);
    };

    // Named SSE events per data-contracts §7
    es.addEventListener("log", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const logEntry: LogEvent = payload.data ?? payload;
        appendLog(logEntry);
      } catch (err) {
        console.error("[SSE] Failed to parse log event", err, e.data);
      }
    });

    es.addEventListener("state", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const stateData = payload.data ?? payload;
        setServers(stateData.servers ?? []);
      } catch (err) {
        console.error("[SSE] Failed to parse state event", err, e.data);
      }
    });

    es.addEventListener("incident", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const incidentData: Incident = payload.data ?? payload;
        setIncident(incidentData);
      } catch (err) {
        console.error("[SSE] Failed to parse incident event", err, e.data);
      }
    });

    // Fallback: some backends emit everything as unnamed "message" events
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
        // non-JSON heartbeat frames are expected
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
      {/* EXECUTION_MODE banner — defaults to SIMULATED when no incident */}
      <ModeBanner mode={incident?.execution_mode ?? "simulate"} />

      {/* Top bar */}
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

      {/* System error banner */}
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

      {/* Main two-panel war room */}
      <main className="flex flex-1 overflow-hidden">
        {/* LEFT — System log */}
        <section className="flex-1 flex flex-col border-r border-zinc-800 overflow-hidden">
          <SystemLog logs={logs} />
        </section>

        {/* RIGHT — Infrastructure tiles + incident detail */}
        <section className="w-96 flex flex-col overflow-hidden border-l border-zinc-800">
          <div className="flex-1 overflow-hidden flex flex-col">
            {/* Infra tiles take up top portion */}
            <div className={incident ? "h-[40%] shrink-0" : "flex-1"}>
              <InfraPanel servers={servers} incident={incident} />
            </div>

            {/* Incident detail panel below tiles when active */}
            {incident && (
              <div className="flex-1 overflow-y-auto">
                <IncidentDetail incident={incident} />
              </div>
            )}
          </div>
        </section>
      </main>

      {/* Bottom trigger / approval bar */}
      <TriggerBar
        apiUrl={API_URL}
        incident={incident}
        onError={(msg) => setSysError(msg)}
      />
    </div>
  );
}
