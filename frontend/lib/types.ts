// Data contracts matching data-contracts.md — snake_case on the wire.

export type LogSource = "AGENT" | "SYSTEM" | "VOICE";

export interface LogEvent {
  source: LogSource;
  message: string;
  ts: string;
}

export type ServerStatus = "healthy" | "compromised" | "isolated";

export interface Server {
  id: string;
  name: string;
  service: string;
  status: ServerStatus;
  depended_on_by: string[];
  container: string;
}

export type IncidentStatus = "awaiting_approval" | "resolved";
export type Decision = "approve" | "deny" | null;

export interface Incident {
  incident_id: string;
  status: IncidentStatus;
  decision: Decision;
  action: string;
  target: string;
  script: string;
  created_at: string;
}

// §6 /execute request body
export interface ExecuteRequest {
  incident_id: string;
  decision: "approve" | "deny";
  action: string;
  target: string;
}

// §1 alert payload (Shellshock)
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
