from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# §1 — Inbound alert
# ---------------------------------------------------------------------------
class Alert(BaseModel):
    alert_id: str
    title: str
    alert_type: str
    priority: str
    tags: list[str]
    body: str
    host: str
    timestamp: str
    # sim_resolves_after is a demo fixture hint — ignored by production logic
    sim_resolves_after: Optional[str] = None


# ---------------------------------------------------------------------------
# §2 — Infrastructure state
# ---------------------------------------------------------------------------
ServerStatus = Literal["healthy", "compromised", "isolated", "degraded", "rolled_back", "recovered"]


class Server(BaseModel):
    id: str
    name: str
    service: str
    status: ServerStatus
    depended_on_by: list[str]
    container: str


class InfraState(BaseModel):
    servers: list[Server]


# ---------------------------------------------------------------------------
# §2b — Deployments state
# ---------------------------------------------------------------------------
class DeploySnapshot(BaseModel):
    deploy_id: str
    commit: str
    deployed_at: str
    healthy: bool


class Deployment(BaseModel):
    service: str
    current: DeploySnapshot
    previous: DeploySnapshot


class DeploymentsState(BaseModel):
    deployments: list[Deployment]


# ---------------------------------------------------------------------------
# §3 — Diagnosis (Agent 1 "Diagnostician" output)
# ---------------------------------------------------------------------------
class ExactLocation(BaseModel):
    service: str
    route: Optional[str] = None
    deploy_id: Optional[str] = None
    commit: Optional[str] = None
    datadog_link: Optional[str] = None


class Diagnosis(BaseModel):
    incident_type: Literal[
        "security", "bad_deploy", "error_spike", "latency", "crash_loop", "resource_exhaustion"
    ]
    severity: str
    affected_service: str
    exact_location: ExactLocation
    blast_radius: list[str]
    runbook: str
    confidence: float
    summary: str
    rationale: str
    cve: Optional[str] = None


# ---------------------------------------------------------------------------
# §4 — Remediation plan (Agent 2 "Strategist" output)
# ---------------------------------------------------------------------------
class RemediationStep(BaseModel):
    action: str
    target: str
    autonomy: Literal["auto", "human"]
    reversible: bool
    description: str


class RemediationPlan(BaseModel):
    summary: str
    steps: list[RemediationStep]
    script: str


# ---------------------------------------------------------------------------
# §5 — Incident object (expanded in v2)
# ---------------------------------------------------------------------------
class Attempt(BaseModel):
    action: str
    target: str
    actor: str
    result: Literal["succeeded", "failed", "denied"]
    ts: str


class AssignedEngineer(BaseModel):
    id: str
    name: str
    channels: list[str]


IncidentStatus = Literal[
    "received",
    "diagnosing",
    "remediating",
    "verifying",
    "escalated",
    "awaiting_approval",
    "resolved",
    "failed",
]


class Incident(BaseModel):
    incident_id: str
    status: IncidentStatus
    execution_mode: str = "simulate"
    diagnosis: Optional[dict] = None
    plan: Optional[dict] = None
    attempts: list[dict] = []
    assigned_engineer: Optional[dict] = None
    decision: Optional[Literal["approve", "deny"]] = None
    created_at: str

    # v1 backward-compat fields (still read by test_api.py)
    action: Optional[str] = None
    target: Optional[str] = None
    script: Optional[str] = None


# ---------------------------------------------------------------------------
# §6 — /execute request body (expanded in v2)
# ---------------------------------------------------------------------------
class ExecuteRequest(BaseModel):
    incident_id: str
    decision: Literal["approve", "deny"]
    action: str
    target: str
    actor: str = "auto"


# ---------------------------------------------------------------------------
# §8 — On-call engineer registry
# ---------------------------------------------------------------------------
class Engineer(BaseModel):
    id: str
    name: str
    slack_id: str
    phone: str
    timezone: str
    shift_start: str
    shift_end: str
    status: Literal["active", "inactive"]


class OnCallRegistry(BaseModel):
    engineers: list[Engineer]


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------
class TriggerResponse(BaseModel):
    incident_id: str


# ---------------------------------------------------------------------------
# §7 — SSE event payload models
# ---------------------------------------------------------------------------
LogSource = Literal["AGENT", "SYSTEM", "REMEDIATION", "SLACK", "VOICE"]


class LogEventData(BaseModel):
    source: LogSource
    message: str
    ts: str


class LogEvent(BaseModel):
    type: Literal["log"] = "log"
    data: LogEventData


class StateEvent(BaseModel):
    type: Literal["state"] = "state"
    data: InfraState


class IncidentEvent(BaseModel):
    type: Literal["incident"] = "incident"
    data: Incident
