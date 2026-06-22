"""
Approval request registry (data-contracts §10).

Pure in-memory CRUD — no event emission here. Callers emit SSE events after
mutations so the registry stays HTTP-free and unit-testable.

Mirrors the pattern in app/incidents.py.
"""
from __future__ import annotations

import asyncio
import random
import string
from datetime import datetime, timezone
from typing import Optional

from app.logging_config import get_logger

logger = get_logger(__name__)

# In-memory registry: request_id -> request dict
_requests: dict[str, dict] = {}

# asyncio.Event per pending blocking waiter: request_id -> Event
_waiters: dict[str, asyncio.Event] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id() -> str:
    suffix = "".join(random.choices(string.hexdigits[:16], k=4))
    return f"apr-{suffix}"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_request(body: dict) -> dict:
    """Assign request_id, created_at, status='created'; store and return."""
    req_id = _gen_id()
    req = dict(body)
    req["request_id"] = req_id
    req["created_at"] = _now_iso()
    req["status"] = "created"
    req.setdefault("assigned_approver", None)
    req.setdefault("outcome", None)
    # Ensure requester is a dict (may arrive as a model or None)
    if req.get("requester") is None:
        req["requester"] = {"source": "agent", "name": None, "tenant": None}
    elif hasattr(req["requester"], "dict"):
        req["requester"] = req["requester"].dict()
    # diagnostics may be a Pydantic model
    if req.get("diagnostics") is not None and hasattr(req["diagnostics"], "dict"):
        req["diagnostics"] = req["diagnostics"].dict()
    _requests[req_id] = req
    logger.info("Created approval request %s (mode=%s, action=%s)", req_id, req.get("mode"), req.get("action"))
    return req


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def get_request(request_id: str) -> Optional[dict]:
    return _requests.get(request_id)


# ---------------------------------------------------------------------------
# Mutators
# ---------------------------------------------------------------------------

def set_status(request_id: str, status: str) -> Optional[dict]:
    req = _requests.get(request_id)
    if req is None:
        logger.warning("set_status: unknown request '%s'", request_id)
        return None
    old = req["status"]
    req["status"] = status
    logger.info("Request %s: status %s → %s", request_id, old, status)
    return req


def set_outcome(request_id: str, outcome: dict) -> Optional[dict]:
    req = _requests.get(request_id)
    if req is None:
        logger.warning("set_outcome: unknown request '%s'", request_id)
        return None
    req["outcome"] = outcome
    return req


# ---------------------------------------------------------------------------
# Blocking-wait helpers
# ---------------------------------------------------------------------------

def register_waiter(request_id: str) -> asyncio.Event:
    """Create and store an asyncio.Event for this request.  Caller awaits it."""
    event = asyncio.Event()
    _waiters[request_id] = event
    return event


def fire_waiter(request_id: str) -> None:
    """Signal the Event for request_id (if one is registered)."""
    event = _waiters.get(request_id)
    if event is not None:
        event.set()


def clear_waiter(request_id: str) -> None:
    """Remove the waiter entry after it has been consumed."""
    _waiters.pop(request_id, None)


# ---------------------------------------------------------------------------
# Resolve (set final decision + status + outcome, fire waiter)
# ---------------------------------------------------------------------------

def resolve_request(
    request_id: str,
    decision: str,
    actor: str,
    detail: Optional[str] = None,
    mode: Optional[str] = None,
) -> Optional[dict]:
    """Record the decision outcome and advance status.

    Status after resolve:
        deny   → "denied"
        timeout → "timed_out"
        approve + gate mode     → "approved"  (caller sets "executed" after running)
        approve + callback mode → "returned"
    """
    req = _requests.get(request_id)
    if req is None:
        logger.warning("resolve_request: unknown request '%s'", request_id)
        return None

    if mode is None:
        mode = req.get("mode", "gate")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    outcome = {
        "request_id": request_id,
        "approved": decision == "approve",
        "decision": decision,
        "actor": actor,
        "decided_at": now,
        "detail": detail,
    }
    req["outcome"] = outcome

    if decision == "approve":
        if mode == "callback":
            req["status"] = "returned"
        else:
            req["status"] = "approved"
    elif decision == "timeout":
        req["status"] = "timed_out"
    else:
        req["status"] = "denied"

    logger.info("Request %s: resolved decision=%s actor=%s status=%s", request_id, decision, actor, req["status"])
    fire_waiter(request_id)
    return req
