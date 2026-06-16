from __future__ import annotations
from fastapi import APIRouter, HTTPException
from app.models import ExecuteRequest, Incident
from app.incidents import get_incident, resolve_incident
from app.state import set_status
from app.events import emit_log, emit_incident

router = APIRouter()


@router.post("/execute", response_model=Incident)
async def execute(req: ExecuteRequest) -> dict:
    inc = get_incident(req.incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail=f"Incident {req.incident_id} not found")

    # Idempotency guard
    if inc["status"] == "resolved":
        emit_log("SYSTEM", f"[WARN] Incident {req.incident_id} already resolved — no-op")
        return inc

    resolved = resolve_incident(req.incident_id, req.decision)
    emit_incident(resolved)

    if req.decision == "approve":
        if req.action == "isolate_container":
            set_status(req.target, "isolated")
            emit_log("SYSTEM", f"Container isolation executed on {req.target}")
        else:
            emit_log("SYSTEM", f"Action {req.action} approved but not implemented — no-op")
    else:
        emit_log("SYSTEM", f"Action {req.action} on {req.target} denied by operator")

    return resolved
