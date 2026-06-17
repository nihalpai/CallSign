"use client";

import { useState } from "react";
import { Incident, ExecuteRequest, AlertPayload } from "@/lib/types";

// Canned alert bodies per data-contracts §1 — scenario picker
const BAD_DEPLOY_ALERT: AlertPayload = {
  alert_id: "dd-2026-0101",
  title: "5xx error rate spike on checkout",
  alert_type: "reliability",
  priority: "P1",
  tags: [
    "service:payment-gw",
    "host:payment-gw",
    "route:/api/checkout",
    "deploy:dpl_9f2",
  ],
  body: "HTTP 5xx on /api/checkout jumped to 40% immediately after deploy dpl_9f2. Rollback candidate.",
  host: "payment-gw",
  timestamp: new Date().toISOString(),
};

const ERROR_SPIKE_ALERT: AlertPayload = {
  alert_id: "dd-2026-0102",
  title: "Error spike on auth service",
  alert_type: "reliability",
  priority: "P2",
  tags: [
    "service:auth-01",
    "host:auth-01",
    "route:/api/auth/token",
  ],
  body: "Error rate on auth-01 spiked to 25%. Possible worker crash or resource exhaustion.",
  host: "auth-01",
  timestamp: new Date().toISOString(),
};

const SHELLSHOCK_ALERT: AlertPayload = {
  alert_id: "dd-2026-0042",
  title: "Remote code execution attempt detected",
  alert_type: "security",
  priority: "P1",
  tags: ["cve:CVE-2026-1337", "service:auth", "host:auth-01"],
  body: "Anomalous bash process spawned via CGI on auth-01. Pattern matches Shellshock-class RCE.",
  host: "auth-01",
  timestamp: new Date().toISOString(),
};

type Scenario = "bad_deploy" | "error_spike" | "shellshock";

const SCENARIOS: { id: Scenario; label: string; alert: AlertPayload }[] = [
  { id: "bad_deploy",   label: "Bad deploy (checkout 5xx)", alert: BAD_DEPLOY_ALERT },
  { id: "error_spike",  label: "Error spike",                alert: ERROR_SPIKE_ALERT },
  { id: "shellshock",   label: "Shellshock RCE",             alert: SHELLSHOCK_ALERT },
];

// Find the current human step needing approval from an incident
function currentHumanStep(
  incident: Incident
): { action: string; target: string } | null {
  if (!incident.plan) return null;
  const { steps } = incident.plan;
  const { attempts } = incident;

  for (const step of steps) {
    if (step.autonomy !== "human") continue;
    const matching = attempts.filter(
      (a) => a.action === step.action && a.target === step.target
    );
    if (
      matching.length === 0 ||
      matching[matching.length - 1].result === "failed"
    ) {
      return { action: step.action, target: step.target };
    }
  }
  return null;
}

interface Props {
  apiUrl: string;
  incident: Incident | null;
  onError?: (msg: string) => void;
}

export default function TriggerBar({ apiUrl, incident, onError }: Props) {
  const [selectedScenario, setSelectedScenario] = useState<Scenario>("bad_deploy");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [deciding, setDeciding] = useState<"approve" | "deny" | null>(null);

  const showApproval = incident?.status === "awaiting_approval";
  const humanStep = incident ? currentHumanStep(incident) : null;
  const selectedLabel =
    SCENARIOS.find((s) => s.id === selectedScenario)?.label ?? selectedScenario;

  async function handleTrigger() {
    const scenario = SCENARIOS.find((s) => s.id === selectedScenario);
    if (!scenario) return;

    setTriggering(true);
    try {
      const res = await fetch(`${apiUrl}/webhook/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...scenario.alert, timestamp: new Date().toISOString() }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        onError?.(`Trigger failed (${res.status}): ${text}`);
        console.error("[TriggerBar] trigger failed", res.status, text);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      onError?.(`Trigger error: ${msg}`);
      console.error("[TriggerBar] trigger error", e);
    } finally {
      setTriggering(false);
    }
  }

  async function handleDecision(decision: "approve" | "deny") {
    if (!incident || !humanStep) return;
    setDeciding(decision);

    const body: ExecuteRequest = {
      incident_id: incident.incident_id,
      decision,
      action: humanStep.action,
      target: humanStep.target,
      actor: incident.assigned_engineer?.id ?? "ui-engineer",
    };

    try {
      const res = await fetch(`${apiUrl}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        onError?.(`Execute failed (${res.status}): ${text}`);
        console.error("[TriggerBar] execute failed", res.status, text);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      onError?.(`Execute error: ${msg}`);
      console.error("[TriggerBar] execute error", e);
    } finally {
      setDeciding(null);
    }
  }

  const approveLabel = humanStep
    ? `[ APPROVE ${humanStep.action.replace(/_/g, " ").toUpperCase()} ]`
    : "[ APPROVE ]";

  return (
    <div className="relative flex items-center gap-4 px-6 py-3 border-t border-zinc-800 bg-zinc-950 shrink-0">
      {/* Scenario picker */}
      <div className="relative">
        <button
          onClick={() => setPickerOpen((o) => !o)}
          disabled={triggering}
          className={[
            "font-mono text-sm px-4 py-2 rounded border transition-colors flex items-center gap-2",
            "border-zinc-600 text-zinc-300 hover:border-zinc-400 hover:text-zinc-200",
            "disabled:opacity-40 disabled:cursor-not-allowed",
          ].join(" ")}
        >
          <span className="text-zinc-500 text-xs">Simulate Alert</span>
          <span className="text-xs text-zinc-300 max-w-[12rem] truncate">{selectedLabel}</span>
          <span className="text-zinc-500">▼</span>
        </button>

        {pickerOpen && (
          <div className="absolute bottom-full mb-1 left-0 z-10 bg-zinc-900 border border-zinc-700 rounded shadow-xl min-w-max">
            {SCENARIOS.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  setSelectedScenario(s.id);
                  setPickerOpen(false);
                }}
                className={[
                  "w-full text-left px-4 py-2 font-mono text-xs hover:bg-zinc-800 transition-colors",
                  s.id === selectedScenario ? "text-cyan-400" : "text-zinc-300",
                ].join(" ")}
              >
                {s.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Fire trigger button */}
      <button
        onClick={handleTrigger}
        disabled={triggering}
        className={[
          "font-mono text-sm px-4 py-2 rounded border transition-colors",
          "border-red-800 text-red-400 hover:border-red-500 hover:text-red-300 hover:bg-red-950/20",
          "disabled:opacity-40 disabled:cursor-not-allowed",
        ].join(" ")}
      >
        {triggering ? "[ FIRING… ]" : "[ FIRE ]"}
      </button>

      {/* Approval buttons — shown only when awaiting_approval */}
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
            {deciding === "approve" ? "[ … ]" : approveLabel}
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

      {/* Resolved / failed notice */}
      {incident?.status === "resolved" && (
        <span className="ml-auto font-mono text-xs text-green-500 tracking-widest">
          ✓ INCIDENT RESOLVED ({incident.decision?.toUpperCase() ?? "AUTO"})
        </span>
      )}
      {incident?.status === "failed" && (
        <span className="ml-auto font-mono text-xs text-red-400 tracking-widest animate-pulse">
          ✗ INCIDENT FAILED — manual intervention required
        </span>
      )}
    </div>
  );
}
