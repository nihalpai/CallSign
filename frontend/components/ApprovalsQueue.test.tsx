import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ApprovalsQueue from "@/components/ApprovalsQueue";
import { ApprovalRequest } from "@/lib/types";

function makeRequest(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    request_id: "apr-0001",
    requester: { source: "agent", name: "support-refund-bot", tenant: null },
    action: "rollback_deployment",
    target: "payment-gw",
    context: "5xx on /api/checkout at 40% since deploy dpl_9f2",
    risk: "high",
    reversible: true,
    mode: "gate",
    created_at: "2026-06-15T09:14:03Z",
    status: "awaiting_approval",
    assigned_approver: { id: "eng-02", name: "Priya" },
    ...overrides,
  };
}

describe("ApprovalsQueue", () => {
  it("shows empty state when no requests", () => {
    render(<ApprovalsQueue requests={[]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText(/No approval requests yet/)).toBeInTheDocument();
  });

  it("renders a row for each request", () => {
    const requests = [
      makeRequest({ request_id: "apr-0001" }),
      makeRequest({ request_id: "apr-0002", requester: { source: "agent", name: "deploy-bot", tenant: null } }),
    ];
    render(<ApprovalsQueue requests={requests} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByTestId("approval-row-apr-0001")).toBeInTheDocument();
    expect(screen.getByTestId("approval-row-apr-0002")).toBeInTheDocument();
  });

  it("renders the requester name", () => {
    render(
      <ApprovalsQueue
        requests={[makeRequest()]}
        selectedId={null}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("support-refund-bot")).toBeInTheDocument();
  });

  it("renders the action", () => {
    render(
      <ApprovalsQueue
        requests={[makeRequest()]}
        selectedId={null}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("rollback_deployment")).toBeInTheDocument();
  });

  it("renders the risk badge", () => {
    render(
      <ApprovalsQueue
        requests={[makeRequest({ risk: "high" })]}
        selectedId={null}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("renders medium risk badge", () => {
    render(
      <ApprovalsQueue
        requests={[makeRequest({ risk: "medium" })]}
        selectedId={null}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("medium")).toBeInTheDocument();
  });

  it("renders the assigned approver name (routed-to)", () => {
    render(
      <ApprovalsQueue
        requests={[makeRequest()]}
        selectedId={null}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText(/Priya/)).toBeInTheDocument();
  });

  it("calls onSelect with the request_id when a row is clicked", () => {
    const onSelect = vi.fn();
    render(
      <ApprovalsQueue
        requests={[makeRequest({ request_id: "apr-abc" })]}
        selectedId={null}
        onSelect={onSelect}
      />
    );
    fireEvent.click(screen.getByTestId("approval-row-apr-abc"));
    expect(onSelect).toHaveBeenCalledWith("apr-abc");
  });

  it("highlights the selected row with a violet border class", () => {
    render(
      <ApprovalsQueue
        requests={[makeRequest({ request_id: "apr-selected" })]}
        selectedId="apr-selected"
        onSelect={() => {}}
      />
    );
    const row = screen.getByTestId("approval-row-apr-selected");
    expect(row.className).toContain("border-violet-500");
  });

  it("does not highlight a non-selected row", () => {
    render(
      <ApprovalsQueue
        requests={[makeRequest({ request_id: "apr-other" })]}
        selectedId="apr-different"
        onSelect={() => {}}
      />
    );
    const row = screen.getByTestId("approval-row-apr-other");
    expect(row.className).not.toContain("border-violet-500");
  });
});
