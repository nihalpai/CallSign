// Data contracts matching data-contracts.md — snake_case on the wire.
// v2: expanded shapes per §2, §3, §4, §5, §6, §7.

export type LogSource = "AGENT" | "SYSTEM" | "VOICE" | "REMEDIATION" | "SLACK";

export interface LogEvent {
  source: LogSource;
  message: string;
  ts: string;
}

export type ServerStatus =
  | "healthy"
  | "compromised"
  | "isolated"
  | "degraded"
  | "rolled_back"
  | "recovered";

export interface Server {
  id: string;
  name: string;
  service: string;
  status: ServerStatus;
  depended_on_by: string[];
  container: string;
}

// §3 — Agent 1 Diagnostician output
export interface ExactLocation {
  service: string;
  route?: string;
  deploy_id?: string;
  commit?: string;
  datadog_link?: string;
}

export interface Diagnosis {
  incident_type: string;
  severity: string;
  affected_service: string;
  exact_location: ExactLocation;
  blast_radius: string[];
  runbook: string;
  confidence: number;
  summary: string;
  rationale: string;
  cve: string | null;
}

// §4 — Agent 2 Strategist output
export interface RemediationStep {
  action: string;
  target: string;
  autonomy: "auto" | "human";
  reversible: boolean;
  description: string;
}

export interface RemediationPlan {
  summary: string;
  steps: RemediationStep[];
  script: string;
}

// §5 — Attempt record inside Incident
export interface Attempt {
  action: string;
  target: string;
  actor: string;
  result: "succeeded" | "failed" | "denied";
  ts: string;
}

export interface AssignedEngineer {
  id: string;
  name: string;
  channels: string[];
}

export type IncidentStatus =
  | "received"
  | "diagnosing"
  | "remediating"
  | "verifying"
  | "escalated"
  | "awaiting_approval"
  | "resolved"
  | "failed";

export type ExecutionMode = "simulate" | "real";
export type Decision = "approve" | "deny" | null;

// §5 — Full incident object
export interface Incident {
  incident_id: string;
  status: IncidentStatus;
  execution_mode: ExecutionMode;
  diagnosis: Diagnosis | null;
  plan: RemediationPlan | null;
  attempts: Attempt[];
  assigned_engineer: AssignedEngineer | null;
  decision: Decision;
  created_at: string;
}

// §6 — /execute request body (expanded with actor)
export interface ExecuteRequest {
  incident_id: string;
  decision: "approve" | "deny";
  action: string;
  target: string;
  actor: string;
}

// §1 — Alert payload for /webhook/trigger
export interface AlertPayload {
  alert_id: string;
  title: string;
  alert_type: string;
  priority: string;
  tags: string[];
  body: string;
  host: string;
  timestamp: string;
}
