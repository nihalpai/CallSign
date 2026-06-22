"""POST /approvals — generic approval-gate front door (data-contracts §10/§11/§12).

Flow per approval-api.md:
  1. Auth via X-API-Key.
  2. Create the ApprovalRequest in-memory.
  3. Emit log + approval SSE.
  4. Enrich (risk, summary, dangers/token inference).
  5. Route to a human (select_approver); post Slack card when SLACK_ENABLED.
  6. wait=blocking → hold until decided or timeout → return DecisionOutcome (§11).
     wait=async    → return {"request_id": ..., "status": "awaiting_approval"} immediately.

GET /approvals/{request_id} — poll status (returns the stored request dict).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Union

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key
from app.events import emit_approval, emit_log
from app.logging_config import get_logger
from app.models import ApprovalCreate, DecisionOutcome
from app.requests import (
    clear_waiter,
    create_request,
    get_request,
    register_waiter,
    resolve_request,
    set_status,
)

logger = get_logger(__name__)

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sse_log(source: str, message: str) -> None:
    emit_log(source, message)


def _try_enrich(req: dict) -> dict:
    try:
        from app.enrichment import enrich_request
        req = enrich_request(req, _sse_log)
    except ImportError:
        pass
    except Exception:
        logger.exception("Enrichment failed for request %s — continuing without it", req.get("request_id"))
    return req


@router.post("/approvals", dependencies=[Depends(require_api_key)])
async def create_approval(body: ApprovalCreate) -> Union[DecisionOutcome, dict]:
    # 1. Build stored request from body
    body_dict = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    req = create_request(body_dict)
    req_id: str = req["request_id"]

    emit_log("SYSTEM", f"Approval request {req_id} received: {req.get('action')}")
    emit_approval(req)

    # 2. Enrich
    from app.config import ENRICH_REQUESTS
    if ENRICH_REQUESTS:
        req = _try_enrich(req)
        emit_approval(req)

    # 3. Route to a human
    set_status(req_id, "awaiting_approval")
    req = get_request(req_id)

    engineer = None
    try:
        from app.escalation import select_approver
        area = req.get("target") or None
        engineer = select_approver(area)
    except Exception:
        logger.exception("select_approver failed for request %s", req_id)

    if engineer:
        req["assigned_approver"] = {"id": engineer.get("id"), "name": engineer.get("name")}
        name = engineer.get("name", "unknown")
        emit_log("SYSTEM", f"Request {req_id} routed to {name}")

        from app.config import SLACK_ENABLED
        if SLACK_ENABLED:
            try:
                from app.integrations.slack import post_approval
                post_approval(req, engineer, _sse_log)
            except Exception:
                logger.exception("Slack post_approval failed for request %s", req_id)
        else:
            dangers = req.get("dangers") or []
            tokens = req.get("estimated_tokens")
            card_hint = f"action={req.get('action')!r} risk={req.get('risk')}"
            if dangers:
                card_hint += f" dangers={dangers}"
            if tokens is not None:
                card_hint += f" estimated_tokens={tokens}"
            emit_log("SLACK", f"would post approval card for {req_id} to {name} — {card_hint}")
    else:
        emit_log("SYSTEM", f"No on-call engineer found for request {req_id} — awaiting manual approval")

    emit_approval(req)

    # 4. Return or wait
    if req.get("wait") == "async":
        return {"request_id": req_id, "status": "awaiting_approval"}

    # Blocking: wait until resolved or timeout
    timeout_sec: int = req.get("timeout_sec", 300)
    event = register_waiter(req_id)
    try:
        await asyncio.wait_for(event.wait(), timeout=float(timeout_sec))
    except asyncio.TimeoutError:
        resolve_request(req_id, "timeout", "system", detail="Timed out waiting for human approval")
        emit_log("SYSTEM", f"Request {req_id} timed out after {timeout_sec}s")
    finally:
        clear_waiter(req_id)

    finished = get_request(req_id)
    outcome = (finished or {}).get("outcome") or {
        "request_id": req_id,
        "approved": False,
        "decision": "timeout",
        "actor": "system",
        "decided_at": _now_iso(),
        "detail": "No outcome recorded",
    }
    emit_approval(finished or req)
    return DecisionOutcome(**outcome)


@router.get("/approvals/{request_id}")
async def get_approval(request_id: str) -> dict:
    req = get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Approval request {request_id} not found")
    return req
