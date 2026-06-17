import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PlanTimeline from "@/components/PlanTimeline";
import { RemediationPlan, Attempt } from "@/lib/types";

const plan: RemediationPlan = {
  summary: "Roll back Payments to the last good deploy; restart if needed; isolate as last resort.",
  steps: [
    {
      action: "rollback_deployment",
      target: "payment-gw",
      autonomy: "auto",
      reversible: true,
      description: "Promote previous good deploy dpl_8e1",
    },
    {
      action: "restart_service",
      target: "payment-gw",
      autonomy: "auto",
      reversible: true,
      description: "Restart workers after rollback",
    },
    {
      action: "isolate_service",
      target: "payment-gw",
      autonomy: "human",
      reversible: true,
      description: "Remove from rotation if rollback fails",
    },
  ],
  script: "Severity one: checkout is failing. Do you approve the rollback?",
};

describe("PlanTimeline render with mixed attempt results", () => {
  it("shows pending for all steps when no attempts exist", () => {
    render(<PlanTimeline plan={plan} attempts={[]} />);
    const rows = screen.getAllByTestId(/plan-step-/);
    expect(rows).toHaveLength(3);
    // The dots (·) are the pending markers
    const pendingMarkers = screen.getAllByText("·");
    // The first two auto steps and human step are all pending
    expect(pendingMarkers.length).toBeGreaterThanOrEqual(2);
  });

  it("marks a succeeded step with a checkmark", () => {
    const attempts: Attempt[] = [
      {
        action: "rollback_deployment",
        target: "payment-gw",
        actor: "auto",
        result: "succeeded",
        ts: "2026-06-15T09:14:05Z",
      },
    ];
    render(<PlanTimeline plan={plan} attempts={attempts} />);
    expect(screen.getByText("✓")).toBeInTheDocument();
  });

  it("marks a failed step with an X", () => {
    const attempts: Attempt[] = [
      {
        action: "rollback_deployment",
        target: "payment-gw",
        actor: "auto",
        result: "failed",
        ts: "2026-06-15T09:14:05Z",
      },
    ];
    render(<PlanTimeline plan={plan} attempts={attempts} />);
    expect(screen.getByText("✗")).toBeInTheDocument();
  });

  it("marks the current human step as needs-you (⚠) when no attempts for it", () => {
    const attempts: Attempt[] = [
      {
        action: "rollback_deployment",
        target: "payment-gw",
        actor: "auto",
        result: "failed",
        ts: "2026-06-15T09:14:05Z",
      },
    ];
    render(<PlanTimeline plan={plan} attempts={attempts} />);
    expect(screen.getByText("⚠")).toBeInTheDocument();
    expect(screen.getByText("needs you")).toBeInTheDocument();
  });

  it("renders mixed results: succeeded + failed + needs-you", () => {
    const attempts: Attempt[] = [
      {
        action: "rollback_deployment",
        target: "payment-gw",
        actor: "auto",
        result: "succeeded",
        ts: "2026-06-15T09:14:05Z",
      },
      {
        action: "restart_service",
        target: "payment-gw",
        actor: "auto",
        result: "failed",
        ts: "2026-06-15T09:15:00Z",
      },
    ];
    render(<PlanTimeline plan={plan} attempts={attempts} />);
    expect(screen.getByText("✓")).toBeInTheDocument();
    expect(screen.getByText("✗")).toBeInTheDocument();
    // isolate_service is the first human step with no attempts — needs-you
    expect(screen.getByText("⚠")).toBeInTheDocument();
  });

  it("renders all step action names and targets", () => {
    render(<PlanTimeline plan={plan} attempts={[]} />);
    expect(screen.getByText("rollback_deployment")).toBeInTheDocument();
    expect(screen.getByText("restart_service")).toBeInTheDocument();
    expect(screen.getByText("isolate_service")).toBeInTheDocument();
    const targets = screen.getAllByText("payment-gw");
    expect(targets).toHaveLength(3);
  });

  it("shows the plan summary", () => {
    render(<PlanTimeline plan={plan} attempts={[]} />);
    expect(
      screen.getByText(/Roll back Payments to the last good deploy/)
    ).toBeInTheDocument();
  });
});
