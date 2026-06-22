import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import ApprovalDetail from "@/components/ApprovalDetail";
import { ApprovalRequest } from "@/lib/types";

function makeRequest(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    request_id: "apr-3c91",
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

describe("ApprovalDetail", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the request id", () => {
    render(<ApprovalDetail request={makeRequest()} apiUrl="http://localhost:8000" />);
    expect(screen.getByText("apr-3c91")).toBeInTheDocument();
  });

  it("renders the requester name", () => {
    render(<ApprovalDetail request={makeRequest()} apiUrl="http://localhost:8000" />);
    expect(screen.getByText("support-refund-bot")).toBeInTheDocument();
  });

  it("renders the action and target", () => {
    render(<ApprovalDetail request={makeRequest()} apiUrl="http://localhost:8000" />);
    expect(screen.getByText("rollback_deployment")).toBeInTheDocument();
    expect(screen.getByText("payment-gw")).toBeInTheDocument();
  });

  it("renders the context text", () => {
    render(<ApprovalDetail request={makeRequest()} apiUrl="http://localhost:8000" />);
    expect(screen.getByText(/5xx on \/api\/checkout/)).toBeInTheDocument();
  });

  it("renders the risk badge", () => {
    render(<ApprovalDetail request={makeRequest({ risk: "high" })} apiUrl="http://localhost:8000" />);
    expect(screen.getByText(/high risk/i)).toBeInTheDocument();
  });

  it("renders dangers as a warning list when present", () => {
    render(
      <ApprovalDetail
        request={makeRequest({ dangers: ["May cause downtime", "Irreversible in prod"] })}
        apiUrl="http://localhost:8000"
      />
    );
    expect(screen.getByText("May cause downtime")).toBeInTheDocument();
    expect(screen.getByText("Irreversible in prod")).toBeInTheDocument();
  });

  it("does not render the dangers section when dangers is absent", () => {
    render(<ApprovalDetail request={makeRequest()} apiUrl="http://localhost:8000" />);
    expect(screen.queryByText("Dangers")).not.toBeInTheDocument();
  });

  it("does not render the dangers section when dangers is an empty array", () => {
    render(
      <ApprovalDetail
        request={makeRequest({ dangers: [] })}
        apiUrl="http://localhost:8000"
      />
    );
    expect(screen.queryByText("Dangers")).not.toBeInTheDocument();
  });

  it("renders estimated_tokens when present", () => {
    render(
      <ApprovalDetail
        request={makeRequest({ estimated_tokens: 1420 })}
        apiUrl="http://localhost:8000"
      />
    );
    expect(screen.getByText(/Estimated Lyzr tokens/)).toBeInTheDocument();
    expect(screen.getByText("1420")).toBeInTheDocument();
  });

  it("does not render estimated_tokens line when absent", () => {
    render(<ApprovalDetail request={makeRequest()} apiUrl="http://localhost:8000" />);
    expect(screen.queryByText(/Estimated Lyzr tokens/)).not.toBeInTheDocument();
  });

  it("shows Approve and Deny buttons when status is awaiting_approval", () => {
    render(
      <ApprovalDetail
        request={makeRequest({ status: "awaiting_approval" })}
        apiUrl="http://localhost:8000"
      />
    );
    expect(screen.getByTestId("btn-approve")).toBeInTheDocument();
    expect(screen.getByTestId("btn-deny")).toBeInTheDocument();
  });

  it("does NOT show Approve/Deny buttons when status is approved", () => {
    render(
      <ApprovalDetail
        request={makeRequest({ status: "approved" })}
        apiUrl="http://localhost:8000"
      />
    );
    expect(screen.queryByTestId("btn-approve")).not.toBeInTheDocument();
    expect(screen.queryByTestId("btn-deny")).not.toBeInTheDocument();
  });

  it("does NOT show Approve/Deny buttons when status is denied", () => {
    render(
      <ApprovalDetail
        request={makeRequest({ status: "denied" })}
        apiUrl="http://localhost:8000"
      />
    );
    expect(screen.queryByTestId("btn-approve")).not.toBeInTheDocument();
  });

  it("POSTs to /execute with approve decision when Approve button is clicked", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true } as Response);
    vi.stubGlobal("fetch", mockFetch);

    render(
      <ApprovalDetail
        request={makeRequest({ status: "awaiting_approval" })}
        apiUrl="http://localhost:8000"
      />
    );

    fireEvent.click(screen.getByTestId("btn-approve"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/execute",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: expect.stringContaining('"decision":"approve"'),
        })
      );
    });
  });

  it("POSTs to /execute with deny decision when Deny button is clicked", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true } as Response);
    vi.stubGlobal("fetch", mockFetch);

    render(
      <ApprovalDetail
        request={makeRequest({ status: "awaiting_approval" })}
        apiUrl="http://localhost:8000"
      />
    );

    fireEvent.click(screen.getByTestId("btn-deny"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8000/execute",
        expect.objectContaining({
          body: expect.stringContaining('"decision":"deny"'),
        })
      );
    });
  });

  it("sends request_id and actor=ui-user in the POST body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true } as Response);
    vi.stubGlobal("fetch", mockFetch);

    render(
      <ApprovalDetail
        request={makeRequest({ request_id: "apr-xyz", status: "awaiting_approval" })}
        apiUrl="http://localhost:8000"
      />
    );

    fireEvent.click(screen.getByTestId("btn-approve"));

    await waitFor(() => {
      const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
      expect(body.request_id).toBe("apr-xyz");
      expect(body.actor).toBe("ui-user");
    });
  });
});
