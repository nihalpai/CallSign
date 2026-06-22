from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


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
# §13b — Diagnostics input (optional caller-supplied logs for enrichment)
# ---------------------------------------------------------------------------
class DiagnosticsInput(BaseModel):
    logs: Optional[str] = None
    stack_trace: Optional[str] = None
    deploys: Optional[list[dict]] = None


# ---------------------------------------------------------------------------
# §12 — Requester identity
# ---------------------------------------------------------------------------
class RequesterIdentity(BaseModel):
    source: str = "agent"
    name: Optional[str] = None
    tenant: Optional[str] = None  # FUTURE: multi-tenant


# ---------------------------------------------------------------------------
# §10 — ApprovalRequest (POST body = ApprovalCreate; stored form = ApprovalRequest)
# ---------------------------------------------------------------------------
class ApprovalCreate(BaseModel):
    """The shape the caller POSTs.  Server assigns request_id, created_at, status."""
    requester: Optional[RequesterIdentity] = None
    action: str
    target: Optional[str] = None
    context: Optional[str] = None
    diagnostics: Optional[DiagnosticsInput] = None
    risk: Optional[str] = None
    reversible: bool = True
    mode: Literal["gate", "callback"] = "gate"
    callback_url: Optional[str] = None
    wait: Literal["blocking", "async"] = "blocking"
    timeout_sec: int = 300
    approvers: Optional[list[str]] = None
    estimated_tokens: Optional[int] = None
    dangers: Optional[list[str]] = None


class ApprovalRequest(BaseModel):
    """Server-side stored form — includes server-assigned fields."""
    request_id: str
    requester: RequesterIdentity
    action: str
    target: Optional[str] = None
    context: Optional[str] = None
    diagnostics: Optional[dict] = None
    risk: Optional[str] = None
    reversible: bool = True
    mode: Literal["gate", "callback"] = "gate"
    callback_url: Optional[str] = None
    wait: Literal["blocking", "async"] = "blocking"
    timeout_sec: int = 300
    approvers: Optional[list[str]] = None
    estimated_tokens: Optional[int] = None
    dangers: Optional[list[str]] = None
    created_at: str
    status: str = "created"
    assigned_approver: Optional[str] = None
    outcome: Optional[dict] = None


# ---------------------------------------------------------------------------
# §11 — Decision outcome (returned by blocking call + POSTed to callback_url)
# ---------------------------------------------------------------------------
class DecisionOutcome(BaseModel):
    request_id: str
    approved: bool
    decision: Literal["approve", "deny", "timeout"]
    actor: Optional[str] = None
    decided_at: Optional[str] = None
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# §6 — /execute request body
# ---------------------------------------------------------------------------
class ExecuteRequest(BaseModel):
    # Accept request_id (preferred) or incident_id (legacy alias)
    request_id: Optional[str] = None
    incident_id: Optional[str] = None
    decision: Literal["approve", "deny"]
    action: Optional[str] = None
    target: Optional[str] = None
    actor: str = "auto"
    detail: Optional[str] = None

    def get_request_id(self) -> Optional[str]:
        """Return the effective request identifier (request_id preferred over incident_id)."""
        return self.request_id or self.incident_id


# ---------------------------------------------------------------------------
# §7 — SSE event payload models
# ---------------------------------------------------------------------------
LogSource = Literal["AGENT", "SYSTEM", "SLACK"]


class LogEventData(BaseModel):
    source: LogSource
    message: str
    ts: str


class LogEvent(BaseModel):
    type: Literal["log"] = "log"
    data: LogEventData
