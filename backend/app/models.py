from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


# §1 — Inbound alert
class Alert(BaseModel):
    alert_id: str
    title: str
    alert_type: str
    priority: str
    tags: list[str]
    body: str
    host: str
    timestamp: str


# §2 — Single server in infrastructure state
class Server(BaseModel):
    id: str
    name: str
    service: str
    status: Literal["healthy", "compromised", "isolated"]
    depended_on_by: list[str]
    container: str


class InfraState(BaseModel):
    servers: list[Server]


# §5 — Incident object
class Incident(BaseModel):
    incident_id: str
    status: Literal["awaiting_approval", "resolved"]
    decision: Optional[Literal["approve", "deny"]] = None
    action: str
    target: str
    script: str
    created_at: str


# §6 — /execute request body
class ExecuteRequest(BaseModel):
    incident_id: str
    decision: Literal["approve", "deny"]
    action: str
    target: str


# Response from /webhook/trigger
class TriggerResponse(BaseModel):
    incident_id: str


# §7 — SSE event payloads (for internal use when constructing events)
class LogEventData(BaseModel):
    source: Literal["AGENT", "SYSTEM", "VOICE"]
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
