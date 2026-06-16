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

  it("renders the isolated label (the demo payoff)", () => {
    render(<ServerTile server={{ ...base, status: "isolated" }} />);
    expect(screen.getByText("[ ISOLATED ]")).toBeInTheDocument();
  });

  it("flags a healthy server as blast radius when marked", () => {
    render(<ServerTile server={base} isBlastRadius />);
    expect(screen.getByText("BLAST RADIUS")).toBeInTheDocument();
  });

  it("does not flag an already-isolated server as blast radius", () => {
    render(<ServerTile server={{ ...base, status: "isolated" }} isBlastRadius />);
    expect(screen.queryByText("BLAST RADIUS")).not.toBeInTheDocument();
  });

  it("always shows server id, name, and container", () => {
    render(<ServerTile server={base} />);
    expect(screen.getByText("auth-01")).toBeInTheDocument();
    expect(screen.getByText("Auth Server")).toBeInTheDocument();
    expect(screen.getByText("auth-svc-prod")).toBeInTheDocument();
  });
});
