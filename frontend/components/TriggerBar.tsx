"use client";

import { useState } from "react";
import { Incident, ExecuteRequest } from "@/lib/types";

// Canned Shellshock alert — data-contracts §1
const SHELLSHOCK_ALERT = {
  alert_id: "dd-2026-0042",
  title: "Remote code execution attempt detected",
  alert_type: "security",
  priority: "P1",
  tags: ["cve:CVE-2026-1337", "service:auth", "host:auth-01"],
  body: "Anomalous bash process spawned via CGI on auth-01. Pattern matches Shellshock-class RCE.",
  host: "auth-01",
  timestamp: new Date().toISOString(),
};

interface Props {
  apiUrl: string;
  incident: Incident | null;
  onError?: (msg: string) => void;
}

export default function TriggerBar({ apiUrl, incident, onError }: Props) {
  const [triggering, setTriggering] = useState(false);
  const [deciding, setDeciding] = useState<"approve" | "deny" | null>(null);

  const showApproval = incident?.status === "awaiting_approval";

  async function handleTrigger() {
    setTriggering(true);
    try {
      const res = await fetch(`${apiUrl}/webhook/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(SHELLSHOCK_ALERT),
      });
      if (!res.ok) {
        const text = await res.text();
        onError?.(`Trigger failed (${res.status}): ${text}`);
      }
    } catch (e) {
      onError?.(`Trigger error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTriggering(false);
    }
  }

  async function handleDecision(decision: "approve" | "deny") {
    if (!incident) return;
    setDeciding(decision);

    const body: ExecuteRequest = {
      incident_id: incident.incident_id,
      decision,
      action: incident.action,
      target: incident.target,
    };

    try {
      const res = await fetch(`${apiUrl}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text();
        onError?.(`Execute failed (${res.status}): ${text}`);
      }
    } catch (e) {
      onError?.(`Execute error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setDeciding(null);
    }
  }

  return (
    <div className="flex items-center gap-4 px-6 py-3 border-t border-zinc-800 bg-zinc-950 shrink-0">
      {/* Trigger button */}
      <button
        onClick={handleTrigger}
        disabled={triggering}
        className={[
          "font-mono text-sm px-4 py-2 rounded border transition-colors",
          "border-zinc-600 text-zinc-300 hover:border-red-500 hover:text-red-400",
          "disabled:opacity-40 disabled:cursor-not-allowed",
        ].join(" ")}
      >
        {triggering ? "[ TRIGGERING… ]" : "[ TRIGGER EXPLOIT ]"}
      </button>

      {/* Approval buttons — Tier 0, shown only when awaiting_approval */}
      {showApproval && (
        <div className="flex items-center gap-3 ml-auto">
          <span className="font-mono text-xs text-amber-400 animate-pulse tracking-widest">
            ▶ AWAITING APPROVAL
          </span>
          <button
            onClick={() => handleDecision("approve")}
            disabled={deciding !== null}
            className={[
              "font-mono text-sm px-5 py-2 rounded border transition-colors font-bold",
              "border-green-600 text-green-400 hover:bg-green-900/30",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            ].join(" ")}
          >
            {deciding === "approve" ? "[ … ]" : "[ APPROVE ]"}
          </button>
          <button
            onClick={() => handleDecision("deny")}
            disabled={deciding !== null}
            className={[
              "font-mono text-sm px-5 py-2 rounded border transition-colors font-bold",
              "border-red-700 text-red-400 hover:bg-red-900/30",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            ].join(" ")}
          >
            {deciding === "deny" ? "[ … ]" : "[ DENY ]"}
          </button>
        </div>
      )}

      {/* Resolved notice */}
      {incident?.status === "resolved" && (
        <span className="ml-auto font-mono text-xs text-green-500 tracking-widest">
          ✓ INCIDENT RESOLVED ({incident.decision?.toUpperCase()})
        </span>
      )}
    </div>
  );
}
