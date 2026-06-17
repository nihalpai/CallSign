"""POST /execute — single entry point for every approval channel.

Body: §6 ExecuteRequest (incident_id, decision, action, target, actor).

Flow:
    - 404 if incident not found.
    - Idempotent no-op + warning log if already resolved or failed.
    - approve → execute_step (runs action, records attempt, resolves/updates).
    - deny   → record decision + attempt, set status "failed", emit log + incident.
    - Returns the updated incident (§5).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.models import ExecuteRequest, Incident
from app.incidents import get_incident, set_decision, set_status, add_attempt
from app.events import emit_log, emit_incident
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

_TERMINAL = {"resolved", "failed"}


@router.post("/execute", response_model=Incident)
async def execute(req: ExecuteRequest) -> dict:
    def log(source: str, message: str) -> None:
        emit_log(source, message)

    inc = get_incident(req.incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail=f"Incident {req.incident_id} not found")

    # Idempotency — already in a terminal state
    if inc["status"] in _TERMINAL:
        log("SYSTEM", f"[WARN] Incident {req.incident_id} already {inc['status']} — no-op")
        return inc

    if req.decision == "approve":
        try:
            from app.remediation.engine import execute_step
            inc = execute_step(inc, req.action, req.target, req.actor, log)
        except Exception:
            logger.exception(
                "execute: execute_step raised for incident %s action=%s",
                req.incident_id, req.action,
            )
            log("SYSTEM", f"execute_step error for incident {req.incident_id} — see server logs")

    elif req.decision == "deny":
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        attempt = {
            "action": req.action,
            "target": req.target,
            "actor": req.actor,
            "result": "denied",
            "ts": ts,
        }
        add_attempt(req.incident_id, attempt)
        set_decision(req.incident_id, "deny")
        set_status(req.incident_id, "failed")
        inc = get_incident(req.incident_id)
        log("SYSTEM", f"Action {req.action} on {req.target} denied by {req.actor}")
        emit_incident(inc)

    return inc
