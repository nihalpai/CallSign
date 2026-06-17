import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import SystemLog from "@/components/SystemLog";
import { LogEvent } from "@/lib/types";

function makeLog(source: LogEvent["source"], message: string): LogEvent {
  return { source, message, ts: "2026-06-15T09:14:05Z" };
}

describe("SystemLog source color tests", () => {
  it("renders SYSTEM logs with dim zinc color", () => {
    render(<SystemLog logs={[makeLog("SYSTEM", "Alert received")]} />);
    const label = screen.getByText(/\[SYSTEM/);
    expect(label.className).toContain("text-zinc-500");
  });

  it("renders AGENT logs with cyan color", () => {
    render(<SystemLog logs={[makeLog("AGENT", "Diagnosing incident")]} />);
    const label = screen.getByText(/\[AGENT/);
    expect(label.className).toContain("text-cyan-400");
  });

  it("renders REMEDIATION logs with violet color", () => {
    render(<SystemLog logs={[makeLog("REMEDIATION", "Rolling back deployment")]} />);
    const label = screen.getByText(/\[REMEDIATION/);
    expect(label.className).toContain("text-violet-400");
  });

  it("renders SLACK logs with green color", () => {
    render(<SystemLog logs={[makeLog("SLACK", "Notified Priya via Slack")]} />);
    const label = screen.getByText(/\[SLACK/);
    expect(label.className).toContain("text-green-400");
  });

  it("renders VOICE logs with amber color", () => {
    render(<SystemLog logs={[makeLog("VOICE", "Calling Priya")]} />);
    const label = screen.getByText(/\[VOICE/);
    expect(label.className).toContain("text-amber-400");
  });

  it("renders multiple logs in order", () => {
    const logs: LogEvent[] = [
      makeLog("SYSTEM", "First event"),
      makeLog("AGENT", "Second event"),
      makeLog("REMEDIATION", "Third event"),
    ];
    render(<SystemLog logs={logs} />);
    expect(screen.getByText("First event")).toBeInTheDocument();
    expect(screen.getByText("Second event")).toBeInTheDocument();
    expect(screen.getByText("Third event")).toBeInTheDocument();
  });

  it("shows the empty state when no logs", () => {
    render(<SystemLog logs={[]} />);
    expect(screen.getByText(/Waiting for events/)).toBeInTheDocument();
  });

  it("shows the event count", () => {
    const logs: LogEvent[] = [makeLog("SYSTEM", "A"), makeLog("AGENT", "B")];
    render(<SystemLog logs={logs} />);
    expect(screen.getByText("2 events")).toBeInTheDocument();
  });

  it("renders the message text alongside the source label", () => {
    render(<SystemLog logs={[makeLog("VOICE", "Approval call placed")]} />);
    expect(screen.getByText("Approval call placed")).toBeInTheDocument();
  });
});
