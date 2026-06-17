"use client";

import { Incident } from "@/lib/types";
import PlanTimeline from "./PlanTimeline";

interface Props {
  incident: Incident;
}

export default function IncidentDetail({ incident }: Props) {
  const { diagnosis, plan, attempts, assigned_engineer, status } = incident;

  return (
    <div className="border-t border-zinc-700 px-4 py-4 font-mono space-y-4 overflow-y-auto">
      {/* Incident header */}
      <div className="flex items-baseline gap-3">
        <span className="text-[10px] text-zinc-500 tracking-widest uppercase">
          Incident
        </span>
        <span className="text-sm text-zinc-200 font-bold tracking-wider">
          {incident.incident_id}
        </span>
        <span
          className={[
            "ml-auto text-[10px] tracking-widest uppercase px-2 py-0.5 rounded border",
            status === "resolved"
              ? "text-green-400 border-green-800"
              : status === "awaiting_approval"
              ? "text-amber-400 border-amber-800 animate-pulse"
              : status === "failed"
              ? "text-red-400 border-red-800"
              : "text-zinc-400 border-zinc-700",
          ].join(" ")}
        >
          {status.replace("_", " ")}
        </span>
      </div>

      {/* Exact location */}
      {diagnosis?.exact_location && (
        <div className="space-y-1">
          <div className="text-[10px] text-zinc-500 tracking-widest uppercase">
            Where
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            {diagnosis.exact_location.route && (
              <span className="text-cyan-400">{diagnosis.exact_location.route}</span>
            )}
            {diagnosis.exact_location.deploy_id && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-zinc-300">
                  deploy{" "}
                  <span className="text-violet-400">{diagnosis.exact_location.deploy_id}</span>
                </span>
              </>
            )}
            {diagnosis.exact_location.commit && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-zinc-500 font-mono">
                  ({diagnosis.exact_location.commit})
                </span>
              </>
            )}
            {diagnosis.exact_location.datadog_link && (
              <>
                <span className="text-zinc-600">·</span>
                <a
                  href={diagnosis.exact_location.datadog_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 transition-colors text-[11px]"
                >
                  [DD&nbsp;↗]
                </a>
              </>
            )}
          </div>
        </div>
      )}

      {/* Diagnosis summary */}
      {diagnosis?.summary && (
        <div className="space-y-1">
          <div className="text-[10px] text-zinc-500 tracking-widest uppercase">Summary</div>
          <p className="text-xs text-zinc-300 leading-relaxed">{diagnosis.summary}</p>
        </div>
      )}

      {/* Remediation plan */}
      {plan && plan.steps.length > 0 && (
        <PlanTimeline plan={plan} attempts={attempts} />
      )}

      {/* Escalation / paging status */}
      {assigned_engineer && (
        <div className="space-y-1">
          <div className="text-[10px] text-zinc-500 tracking-widest uppercase">Paged</div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-zinc-200 font-bold">{assigned_engineer.name}</span>
            <span className="text-zinc-600">via</span>
            {assigned_engineer.channels.map((ch) => (
              <span
                key={ch}
                className={[
                  "px-1.5 py-0.5 rounded text-[10px] tracking-widest uppercase border",
                  ch === "slack"
                    ? "text-green-400 border-green-800"
                    : ch === "voice"
                    ? "text-amber-400 border-amber-800"
                    : "text-zinc-400 border-zinc-700",
                ].join(" ")}
              >
                {ch}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Voice script when awaiting approval */}
      {status === "awaiting_approval" && plan?.script && (
        <div className="space-y-1 p-3 bg-amber-950/20 border border-amber-800/40 rounded">
          <div className="text-[10px] text-amber-500 tracking-widest uppercase">
            Voice Script
          </div>
          <p className="text-xs text-amber-200 leading-relaxed">{plan.script}</p>
        </div>
      )}
    </div>
  );
}
