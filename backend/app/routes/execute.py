"""POST /execute — decision sink for approval requests.

Accepts ExecuteRequest with request_id (or incident_id alias) + decision + actor.

On a decision:
  - resolve_request sets status + outcome (already fires_waiter internally).
  - Best-effort POST to callback_url if set.
  - emit_approval to push the updated request to SSE subscribers.

There is no gate-execution here — the calling agent performs its own action after
receiving the approved DecisionOutcome.  Gate/real-execution is reserved for a future
provider adapter layer; see docs/remediation.md.

Idempotent: already-decided requests return a no-op response.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from app.models import ExecuteRequest
from app.events import emit_log, emit_approval
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

_TERMINAL_APR = {"approved", "denied", "returned", "executed", "timed_out"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _post_callback(req_id: str, url: str, outcome: dict) -> None:
    try:
        import httpx
        resp = httpx.post(url, json=outcome, timeout=10.0)
        logger.info("Callback for %s → %s: HTTP %s", req_id, url, resp.status_code)
    except Exception:
        logger.exception("Callback delivery failed for request %s → %s", req_id, url)
        emit_log("SYSTEM", f"[WARN] Callback delivery failed for {req_id} → {url}")


@router.post("/execute")
async def execute(req: ExecuteRequest) -> dict:
    from app.requests import get_request, resolve_request

    req_id = req.get_request_id()
    if not req_id:
        raise HTTPException(status_code=422, detail="request_id or incident_id is required")

    stored = get_request(req_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Approval request {req_id} not found")

    # Idempotency guard
    if stored.get("status") in _TERMINAL_APR:
        emit_log("SYSTEM", f"[WARN] Request {req_id} already {stored['status']} — no-op")
        return stored

    decision = req.decision
    stored = resolve_request(req_id, decision, req.actor, detail=req.detail)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Approval request {req_id} not found")

    emit_log("SYSTEM", f"Request {req_id} {decision} by {req.actor}")
    emit_approval(stored)

    # Best-effort callback delivery
    callback_url = stored.get("callback_url")
    outcome = stored.get("outcome")
    if callback_url and outcome:
        _post_callback(req_id, callback_url, outcome)

    # Post Slack thread with resolution
    try:
        from app.integrations.slack import post_thread
        label = "✅ Approved" if decision == "approve" else "❌ Denied"
        post_thread(stored, f"{label} by {req.actor}", emit_log)
    except Exception:
        logger.exception("post_thread failed for request %s", req_id)

    return stored
