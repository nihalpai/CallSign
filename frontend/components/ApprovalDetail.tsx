"use client";

import { useState } from "react";
import { ApprovalRequest } from "@/lib/types";

interface Props {
  request: ApprovalRequest;
  apiUrl: string;
  onError?: (msg: string) => void;
}

export default function ApprovalDetail({ request, apiUrl, onError }: Props) {
  const [deciding, setDeciding] = useState<"approve" | "deny" | null>(null);

  const canDecide = request.status === "awaiting_approval";

  async function handleDecision(decision: "approve" | "deny") {
    setDeciding(decision);
    try {
      const res = await fetch(`${apiUrl}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: request.request_id,
          decision,
          actor: "ui-user",
        }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        onError?.(`Execute failed (${res.status}): ${text}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      onError?.(`Execute error: ${msg}`);
    } finally {
      setDeciding(null);
    }
  }

  const riskColor =
    request.risk === "high"
      ? "text-red-400 border-red-800"
      : request.risk === "medium"
      ? "text-amber-400 border-amber-800"
      : "text-green-400 border-green-800";

  return (
    <div className="border-t border-zinc-700 px-4 py-4 font-mono space-y-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-baseline gap-3 flex-wrap">
        <span className="text-[10px] text-zinc-500 tracking-widest uppercase">
          Request
        </span>
        <span className="text-sm text-zinc-200 font-bold tracking-wider">
          {request.request_id}
        </span>
        <span
          className={[
            "ml-auto text-[10px] tracking-widest uppercase px-2 py-0.5 rounded border",
            riskColor,
          ].join(" ")}
        >
          {request.risk} risk
        </span>
      </div>

      {/* Requester */}
      <div className="space-y-1">
        <div className="text-[10px] text-zinc-500 tracking-widest uppercase">
          From
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-zinc-500 uppercase tracking-widest text-[10px]">
            {request.requester.source}
          </span>
          <span className="text-zinc-300 font-bold">{request.requester.name}</span>
        </div>
      </div>

      {/* Action + target */}
      <div className="space-y-1">
        <div className="text-[10px] text-zinc-500 tracking-widest uppercase">
          Action
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-violet-400 font-bold">{request.action}</span>
          <span className="text-zinc-600">on</span>
          <span className="text-zinc-200">{request.target}</span>
          {request.reversible === false && (
            <span className="text-red-500 text-[10px] uppercase tracking-wider">
              irreversible
            </span>
          )}
        </div>
      </div>

      {/* Context */}
      {request.context && (
        <div className="space-y-1">
          <div className="text-[10px] text-zinc-500 tracking-widest uppercase">
            Context
          </div>
          <p className="text-xs text-zinc-300 leading-relaxed">{request.context}</p>
        </div>
      )}

      {/* Dangers warning list */}
      {request.dangers && request.dangers.length > 0 && (
        <div className="space-y-1.5 p-3 bg-red-950/20 border border-red-800/50 rounded">
          <div className="text-[10px] text-red-400 tracking-widest uppercase font-bold">
            Dangers
          </div>
          <ul className="space-y-1">
            {request.dangers.map((danger, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-red-300">
                <span className="text-red-500 shrink-0 mt-0.5">▲</span>
                <span>{danger}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Enrichment summary */}
      {request.enrichment_summary && (
        <div className="space-y-1">
          <div className="text-[10px] text-zinc-500 tracking-widest uppercase">
            Enrichment
          </div>
          <p className="text-xs text-zinc-400 leading-relaxed italic">
            {request.enrichment_summary}
          </p>
        </div>
      )}

      {/* Estimated Lyzr tokens */}
      {request.estimated_tokens !== undefined && (
        <div className="text-[10px] text-zinc-600 tracking-widest">
          Estimated Lyzr tokens:{" "}
          <span className="text-zinc-400">{request.estimated_tokens}</span>
        </div>
      )}

      {/* Assigned approver */}
      {request.assigned_approver && (
        <div className="space-y-1">
          <div className="text-[10px] text-zinc-500 tracking-widest uppercase">
            Routed To
          </div>
          <span className="text-xs text-green-400 font-bold">
            {request.assigned_approver.name}
          </span>
        </div>
      )}

      {/* Outcome banner */}
      {request.outcome && (
        <div
          className={[
            "p-3 rounded border text-xs space-y-1",
            request.outcome.decision === "approve"
              ? "bg-green-950/20 border-green-800/40"
              : request.outcome.decision === "deny"
              ? "bg-red-950/20 border-red-800/40"
              : "bg-zinc-800/40 border-zinc-700",
          ].join(" ")}
        >
          <div className="text-[10px] text-zinc-500 tracking-widest uppercase">
            Outcome
          </div>
          <div className="flex items-center gap-2">
            <span
              className={
                request.outcome.decision === "approve"
                  ? "text-green-400 font-bold"
                  : request.outcome.decision === "deny"
                  ? "text-red-400 font-bold"
                  : "text-zinc-400"
              }
            >
              {request.outcome.decision.toUpperCase()}
            </span>
            <span className="text-zinc-600">by</span>
            <span className="text-zinc-300">{request.outcome.actor}</span>
          </div>
          {request.outcome.detail && (
            <p className="text-zinc-400 leading-relaxed">{request.outcome.detail}</p>
          )}
        </div>
      )}

      {/* Approve / Deny buttons — only when awaiting_approval */}
      {canDecide && (
        <div className="flex items-center gap-3 pt-2">
          <span className="font-mono text-xs text-amber-400 animate-pulse tracking-widest mr-auto">
            ▶ AWAITING YOUR DECISION
          </span>
          <button
            data-testid="btn-approve"
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
            data-testid="btn-deny"
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
    </div>
  );
}
