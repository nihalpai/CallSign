"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { LogEvent, ApprovalRequest } from "@/lib/types";
import SystemLog from "@/components/SystemLog";
import ApprovalsQueue from "@/components/ApprovalsQueue";
import ApprovalDetail from "@/components/ApprovalDetail";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Page() {
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [approvals, setApprovals] = useState<Record<string, ApprovalRequest>>({});
  const [selectedApprovalId, setSelectedApprovalId] = useState<string | null>(null);
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

    es.addEventListener("log", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const logEntry: LogEvent = payload.data ?? payload;
        appendLog(logEntry);
      } catch (err) {
        console.error("[SSE] Failed to parse log event", err, e.data);
      }
    });

    es.addEventListener("approval", (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        const approvalData: ApprovalRequest = payload.data ?? payload;
        setApprovals((prev) => ({ ...prev, [approvalData.request_id]: approvalData }));
      } catch (err) {
        console.error("[SSE] Failed to parse approval event", err, e.data);
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
        } else if (type === "approval") {
          const a = data as ApprovalRequest;
          setApprovals((prev) => ({ ...prev, [a.request_id]: a }));
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

  const pendingCount = Object.values(approvals).filter(
    (r) => r.status === "awaiting_approval"
  ).length;

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-mono font-bold text-lg tracking-widest text-zinc-100">
            CALLSIGN
          </span>
          <span className="font-mono text-xs text-zinc-500 tracking-widest uppercase pt-0.5">
            APPROVAL GATE
          </span>
        </div>

        <div className="flex items-center gap-4">
          {pendingCount > 0 && (
            <span className="font-mono text-xs text-amber-400 animate-pulse tracking-widest uppercase">
              {pendingCount} pending
            </span>
          )}
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

      {/* Main layout: log | approvals queue + detail */}
      <main className="flex flex-1 overflow-hidden">
        {/* LEFT — System log */}
        <section className="flex-1 flex flex-col border-r border-zinc-800 overflow-hidden">
          <SystemLog logs={logs} />
        </section>

        {/* RIGHT — Approvals queue + selected detail */}
        <section className="w-[480px] flex flex-col overflow-hidden">
          {/* Queue header */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 shrink-0">
            <span className="font-mono text-[10px] text-zinc-500 tracking-widest uppercase">
              Approvals Queue
            </span>
            {Object.keys(approvals).length > 0 && (
              <span className="font-mono text-[10px] text-zinc-600">
                {Object.keys(approvals).length} request
                {Object.keys(approvals).length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {/* Queue list (top portion when a request is selected) */}
          <div
            className={
              selectedApprovalId
                ? "h-[35%] shrink-0 overflow-y-auto border-b border-zinc-800"
                : "flex-1 overflow-y-auto"
            }
          >
            <ApprovalsQueue
              requests={Object.values(approvals)}
              selectedId={selectedApprovalId}
              onSelect={setSelectedApprovalId}
            />
          </div>

          {/* Selected request detail */}
          {selectedApprovalId && approvals[selectedApprovalId] && (
            <div className="flex-1 overflow-y-auto">
              <ApprovalDetail
                request={approvals[selectedApprovalId]}
                apiUrl={API_URL}
                onError={(msg) => setSysError(msg)}
              />
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
