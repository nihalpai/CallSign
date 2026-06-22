// Data contracts matching data-contracts.md — snake_case on the wire.

export type LogSource = "AGENT" | "SYSTEM" | "VOICE" | "REMEDIATION" | "SLACK";

export interface LogEvent {
  source: LogSource;
  message: string;
  ts: string;
}

// §11 — Decision outcome / callback payload
export type ApprovalDecision = "approve" | "deny" | "timeout";

export interface DecisionOutcome {
  request_id: string;
  approved: boolean;
  decision: ApprovalDecision;
  actor: string;
  decided_at: string;
  detail?: string;
}

// §12 — Requester identity
export interface RequesterIdentity {
  source: "agent" | "incident" | "datadog";
  name: string;
  tenant: string | null;
}

// §10 — ApprovalRequest — core object
export type ApprovalRequestStatus =
  | "created"
  | "awaiting_approval"
  | "approved"
  | "denied"
  | "timed_out"
  | "executed"
  | "returned";

export type RiskLevel = "low" | "medium" | "high";
export type ApprovalMode = "gate" | "callback";
export type WaitMode = "blocking" | "async";

export interface AssignedApprover {
  id: string;
  name: string;
}

export interface ApprovalRequest {
  request_id: string;
  requester: RequesterIdentity;
  action: string;
  target: string;
  context: string;
  risk: RiskLevel;
  reversible?: boolean;
  mode: ApprovalMode;
  callback_url?: string;
  wait?: WaitMode;
  timeout_sec?: number;
  approvers?: string[];
  created_at: string;
  status: ApprovalRequestStatus;
  // Enrichment fields set by backend after triage
  enrichment_summary?: string;
  assigned_approver?: AssignedApprover;
  outcome?: DecisionOutcome;
  // Danger warnings from enrichment
  dangers?: string[];
  // Token cost estimate from Lyzr enrichment
  estimated_tokens?: number;
}
