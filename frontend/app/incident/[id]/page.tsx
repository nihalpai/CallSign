"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { Incident, LogEvent, Server } from "@/lib/types";
import ModeBanner from "@/components/ModeBanner";
import IncidentDetail from "@/components/IncidentDetail";
import InfraPanel from "@/components/InfraPanel";
import SystemLog from "@/components/SystemLog";
import TriggerBar from "@/components/TriggerBar";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type FetchState = "loading" | "ok" | "error";

export default function IncidentPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : (params.id?.[0] ?? "");

  const [incident, setIncident] = useState<Incident | null>(null);
  const [servers, setServers] = useState<Server[]>([]);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [sysError, setSysError] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);

  // Initial fetch of the incident
  useEffect(() => {
    if (!id) return;

    setFetchState("loading");
    fetch(`${API_URL}/incident/${id}`)
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text().catch(() => res.statusText);
          throw new Error(`HTTP ${res.status}: ${text}`);
        }
        return res.json() as Promise<Incident>;
      })
      .then((data) => {
        setIncident(data);
        setFetchState("ok");
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[IncidentPage] fetch failed", err);
        setFetchError(msg);
        setFetchState("error");
      });
  }, [id]);

  const appendLog = useCallback((entry: LogEvent) => {
    setLogs((prev) => [...prev, entry]);
  }, []);

  // Subscribe to live stream for updates
  useEffect(() => {
    const es = new EventSource(`${API_URL}/stream`);
    esRef.current = es;

    es.onerror = (e) => {
      console.error("[IncidentPage SSE] EventSource error", e);
    };

    es.addEventListener("log", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        appendLog(payload.data ?? payload);
      } catch (err) {
        console.error("[IncidentPage SSE] Failed to parse log", err);
      }
    });

    es.addEventListener("state", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const stateData = payload.data ?? payload;
        setServers(stateData.servers ?? []);
      } catch (err) {
        console.error("[IncidentPage SSE] Failed to parse state", err);
      }
    });

    es.addEventListener("incident", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const inc: Incident = payload.data ?? payload;
        // Only apply if it's the same incident we're viewing
        if (!inc.incident_id || inc.incident_id === id) {
          setIncident(inc);
        }
      } catch (err) {
        console.error("[IncidentPage SSE] Failed to parse incident", err);
      }
    });

    es.onmessage = (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const type: string = payload.type;
        const data = payload.data ?? payload;
        if (type === "log") appendLog(data as LogEvent);
        else if (type === "state") setServers((data as { servers: Server[] }).servers ?? []);
        else if (type === "incident") {
          const inc = data as Incident;
          if (!inc.incident_id || inc.incident_id === id) setIncident(inc);
        }
      } catch {
        // heartbeat
      }
    };

    return () => {
      es.close();
    };
  }, [id, appendLog]);

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      <ModeBanner mode={incident?.execution_mode ?? "simulate"} />

      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="font-mono text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            ← WAR ROOM
          </a>
          <span className="text-zinc-700">|</span>
          <span className="font-mono font-bold text-lg tracking-widest text-zinc-100">
            CALLSIGN
          </span>
          <span className="font-mono text-xs text-zinc-500 tracking-widest uppercase pt-0.5">
            Incident {id}
          </span>
        </div>
      </header>

      {/* Fetch error */}
      {fetchState === "error" && (
        <div className="px-6 py-3 bg-red-950/60 border-b border-red-800 font-mono text-xs text-red-400">
          Failed to load incident {id}: {fetchError}
        </div>
      )}

      {/* Loading state */}
      {fetchState === "loading" && (
        <div className="px-6 py-4 font-mono text-sm text-zinc-500 animate-pulse">
          Loading incident {id}…
        </div>
      )}

      {/* System error */}
      {sysError && (
        <div className="px-6 py-2 bg-red-950/60 border-b border-red-800 font-mono text-xs text-red-400">
          {sysError}
          <button onClick={() => setSysError(null)} className="ml-4 text-red-600 hover:text-red-400">
            [dismiss]
          </button>
        </div>
      )}

      {/* Main layout */}
      <main className="flex flex-1 overflow-hidden">
        {/* LEFT — System log */}
        <section className="flex-1 flex flex-col border-r border-zinc-800 overflow-hidden">
          <SystemLog logs={logs} />
        </section>

        {/* RIGHT — Infra + incident detail */}
        <section className="w-96 flex flex-col overflow-hidden border-l border-zinc-800">
          <div className="flex-1 overflow-hidden flex flex-col">
            <div className={incident ? "h-[40%] shrink-0" : "flex-1"}>
              <InfraPanel servers={servers} incident={incident} />
            </div>
            {incident && (
              <div className="flex-1 overflow-y-auto">
                <IncidentDetail incident={incident} />
              </div>
            )}
          </div>
        </section>
      </main>

      <TriggerBar
        apiUrl={API_URL}
        incident={incident}
        onError={(msg) => setSysError(msg)}
      />
    </div>
  );
}
