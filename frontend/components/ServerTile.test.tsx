import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ServerTile from "@/components/ServerTile";
import { Server } from "@/lib/types";

const base: Server = {
  id: "auth-01",
  name: "Auth Server",
  service: "Authentication",
  status: "healthy",
  depended_on_by: ["payment-gw"],
  container: "auth-svc-prod",
};

describe("ServerTile status → visual mapping", () => {
  it("renders the healthy label", () => {
    render(<ServerTile server={base} />);
    expect(screen.getByText("[ HEALTHY ]")).toBeInTheDocument();
  });

  it("blinks the compromised label", () => {
    render(<ServerTile server={{ ...base, status: "compromised" }} />);
    const label = screen.getByText("[COMPROMISED]");
    expect(label.className).toContain("animate-[blink");
  });

  it("blinks the degraded label (reliability incident)", () => {
    render(<ServerTile server={{ ...base, status: "degraded" }} />);
    const label = screen.getByText("[ DEGRADED ]");
    expect(label.className).toContain("animate-[blink");
  });

  it("renders the isolated label with grey styling", () => {
    render(<ServerTile server={{ ...base, status: "isolated" }} />);
    const label = screen.getByText("[ ISOLATED ]");
    expect(label).toBeInTheDocument();
    expect(label.className).toContain("text-zinc-400");
  });

  it("renders the rolled_back label with blue styling", () => {
    render(<ServerTile server={{ ...base, status: "rolled_back" }} />);
    const label = screen.getByText("[ROLLED BACK]");
    expect(label).toBeInTheDocument();
    expect(label.className).toContain("text-blue-400");
  });

  it("renders the recovered label with green styling", () => {
    render(<ServerTile server={{ ...base, status: "recovered" }} />);
    const label = screen.getByText("[ RECOVERED ]");
    expect(label).toBeInTheDocument();
    expect(label.className).toContain("text-green-400");
  });

  it("flags a healthy server as blast radius when marked", () => {
    render(<ServerTile server={base} isBlastRadius />);
    expect(screen.getByText("BLAST RADIUS")).toBeInTheDocument();
  });

  it("does not show blast radius badge when server is already affected", () => {
    render(<ServerTile server={{ ...base, status: "degraded" }} isBlastRadius />);
    expect(screen.queryByText("BLAST RADIUS")).not.toBeInTheDocument();
  });

  it("does not flag an already-isolated server as blast radius", () => {
    render(<ServerTile server={{ ...base, status: "isolated" }} isBlastRadius />);
    expect(screen.queryByText("BLAST RADIUS")).not.toBeInTheDocument();
  });

  it("does not flag a recovered server as blast radius", () => {
    render(<ServerTile server={{ ...base, status: "recovered" }} isBlastRadius />);
    expect(screen.queryByText("BLAST RADIUS")).not.toBeInTheDocument();
  });

  it("always shows server id, name, and container", () => {
    render(<ServerTile server={base} />);
    expect(screen.getByText("auth-01")).toBeInTheDocument();
    expect(screen.getByText("Auth Server")).toBeInTheDocument();
    expect(screen.getByText("auth-svc-prod")).toBeInTheDocument();
  });

  it("renders with a data-testid for each server", () => {
    render(<ServerTile server={base} />);
    expect(screen.getByTestId("server-tile-auth-01")).toBeInTheDocument();
  });
});
