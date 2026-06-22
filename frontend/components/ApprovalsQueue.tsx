"use client";

import { ApprovalRequest, RiskLevel } from "@/lib/types";

interface Props {
  requests: ApprovalRequest[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const RISK_STYLES: Record<RiskLevel, string> = {
  high: "text-red-400 border-red-800",
  medium: "text-amber-400 border-amber-800",
  low: "text-green-400 border-green-800",
};

const STATUS_COLORS: Record<string, string> = {
  awaiting_approval: "text-amber-400",
  approved: "text-green-400",
  denied: "text-red-400",
  executed: "text-blue-400",
  timed_out: "text-zinc-500",
  returned: "text-cyan-400",
  created: "text-zinc-400",
};

export default function ApprovalsQueue({ requests, selectedId, onSelect }: Props) {
  if (requests.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="font-mono text-xs text-zinc-600 tracking-widest">
          No approval requests yet
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col divide-y divide-zinc-800 overflow-y-auto">
      {requests.map((req) => {
        const isSelected = req.request_id === selectedId;
        const riskStyle = RISK_STYLES[req.risk] ?? "text-zinc-400 border-zinc-700";
        const statusColor = STATUS_COLORS[req.status] ?? "text-zinc-400";
        const isPending = req.status === "awaiting_approval";

        return (
          <button
            key={req.request_id}
            data-testid={`approval-row-${req.request_id}`}
            onClick={() => onSelect(req.request_id)}
            className={[
              "w-full text-left px-4 py-3 font-mono transition-colors",
              isSelected
                ? "bg-zinc-800/60 border-l-2 border-violet-500"
                : "hover:bg-zinc-900/60 border-l-2 border-transparent",
            ].join(" ")}
          >
            {/* Row top: requester + risk badge */}
            <div className="flex items-center justify-between gap-2 mb-1">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-[10px] text-zinc-500 tracking-widest uppercase shrink-0">
                  {req.requester.source}
                </span>
                <span className="text-xs text-zinc-200 truncate font-bold">
                  {req.requester.name}
                </span>
              </div>

              <span
                className={[
                  "shrink-0 text-[10px] tracking-widest uppercase px-1.5 py-0.5 rounded border",
                  riskStyle,
                ].join(" ")}
              >
                {req.risk}
              </span>
            </div>

            {/* Action + target */}
            <div className="flex items-center gap-1.5 text-xs mb-1">
              <span className="text-violet-400 truncate">{req.action}</span>
              <span className="text-zinc-600">→</span>
              <span className="text-zinc-300 truncate">{req.target}</span>
            </div>

            {/* Bottom: status + routed-to */}
            <div className="flex items-center gap-3 text-[10px] tracking-widest uppercase">
              <span className={[statusColor, isPending ? "animate-pulse" : ""].join(" ")}>
                {req.status.replace(/_/g, " ")}
              </span>
              {req.assigned_approver && (
                <>
                  <span className="text-zinc-700">·</span>
                  <span className="text-zinc-500 normal-case tracking-normal">
                    → {req.assigned_approver.name}
                  </span>
                </>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
