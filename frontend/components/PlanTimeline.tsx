"use client";

import { Attempt, RemediationPlan, RemediationStep } from "@/lib/types";

interface Props {
  plan: RemediationPlan;
  attempts: Attempt[];
}

type StepResult = "succeeded" | "failed" | "pending" | "needs-you";

function resolveStepResult(
  step: RemediationStep,
  attempts: Attempt[],
  isCurrentHumanStep: boolean
): StepResult {
  // Find the most recent attempt for this step's action+target combo
  const matching = attempts.filter(
    (a) => a.action === step.action && a.target === step.target
  );
  if (matching.length === 0) {
    if (step.autonomy === "human" && isCurrentHumanStep) return "needs-you";
    return "pending";
  }
  const latest = matching[matching.length - 1];
  if (latest.result === "succeeded") return "succeeded";
  if (latest.result === "failed" || latest.result === "denied") return "failed";
  return "pending";
}

const RESULT_ICON: Record<StepResult, string> = {
  succeeded: "✓",
  failed:    "✗",
  pending:   "·",
  "needs-you": "⚠",
};

const RESULT_COLOR: Record<StepResult, string> = {
  succeeded:   "text-green-400",
  failed:      "text-red-400",
  pending:     "text-zinc-500",
  "needs-you": "text-amber-400",
};

const RESULT_LABEL: Record<StepResult, string> = {
  succeeded:   "succeeded",
  failed:      "failed",
  pending:     "pending",
  "needs-you": "needs you",
};

export default function PlanTimeline({ plan, attempts }: Props) {
  // Find the first unresolved human step (the one that needs approval)
  const firstHumanStepIdx = plan.steps.findIndex((s) => {
    if (s.autonomy !== "human") return false;
    const matching = attempts.filter(
      (a) => a.action === s.action && a.target === s.target
    );
    return matching.length === 0 || matching[matching.length - 1].result === "failed";
  });

  return (
    <div className="space-y-1">
      <div className="text-[10px] text-zinc-500 tracking-widest uppercase mb-2 font-mono">
        Remediation Plan
      </div>
      <div className="text-xs text-zinc-400 font-mono mb-3 leading-snug">
        {plan.summary}
      </div>
      <div className="space-y-1.5">
        {plan.steps.map((step, idx) => {
          const isCurrentHumanStep = idx === firstHumanStepIdx;
          const result = resolveStepResult(step, attempts, isCurrentHumanStep);
          const icon = RESULT_ICON[result];
          const color = RESULT_COLOR[result];
          const label = RESULT_LABEL[result];

          return (
            <div
              key={`${step.action}-${step.target}-${idx}`}
              data-testid={`plan-step-${idx}`}
              className={[
                "flex items-start gap-2 font-mono text-xs rounded px-2 py-1.5",
                result === "needs-you" ? "bg-amber-950/30 border border-amber-800/40" : "",
                result === "succeeded" ? "opacity-70" : "",
              ].join(" ")}
            >
              {/* step number */}
              <span className="text-zinc-600 shrink-0 select-none">
                {String(idx + 1).padStart(2, "0")}
              </span>

              {/* status icon */}
              <span className={`shrink-0 font-bold w-3 ${color}`}>{icon}</span>

              {/* action + target */}
              <div className="flex-1 min-w-0">
                <span className="text-zinc-200">{step.action}</span>
                <span className="text-zinc-500 mx-1">→</span>
                <span className="text-cyan-400">{step.target}</span>
                {step.autonomy === "auto" && (
                  <span className="ml-2 text-[10px] text-zinc-600 tracking-wide">AUTO</span>
                )}
              </div>

              {/* result label */}
              <span className={`shrink-0 text-[10px] tracking-widest uppercase ${color}`}>
                {label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
