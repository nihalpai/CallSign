"""
Incident registry (data-contracts §5).

Pure in-memory CRUD — no event emission here. Callers emit SSE events after
mutations so the registry stays HTTP-free and unit-testable.
"""
from __future__ import annotations
import random
import string
from datetime import datetime, timezone
from typing import Optional

from app.logging_config import get_logger

logger = get_logger(__name__)

# In-memory registry: incident_id -> incident dict
_incidents: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id() -> str:
    suffix = "".join(random.choices(string.hexdigits[:16], k=4))
    return f"inc-{suffix}"


# ---------------------------------------------------------------------------
# Open
# ---------------------------------------------------------------------------

def open_incident(alert: dict, execution_mode: str = "simulate") -> dict:
    """Create a new incident from an alert dict.  Status starts as 'diagnosing'."""
    inc_id = _gen_id()

    # Derive v1 backward-compat fields from the alert so test_api.py keeps passing.
    # These are overwritten as the brain and plan are attached.
    inc = {
        "incident_id": inc_id,
        "status": "diagnosing",
        "execution_mode": execution_mode,
        "diagnosis": None,
        "plan": None,
        "attempts": [],
        "assigned_engineer": None,
        "decision": None,
        "created_at": _now_iso(),
        # v1 compat — resolved by the brain / route layer
        "action": None,
        "target": alert.get("host"),
        "script": None,
    }
    _incidents[inc_id] = inc
    logger.info("Opened incident %s (mode=%s, host=%s)", inc_id, execution_mode, alert.get("host"))
    return inc


# ---------------------------------------------------------------------------
# Mutators — all return the updated incident or None if not found
# ---------------------------------------------------------------------------

def set_diagnosis(incident_id: str, diagnosis: dict) -> Optional[dict]:
    inc = _incidents.get(incident_id)
    if inc is None:
        logger.warning("set_diagnosis: unknown incident '%s'", incident_id)
        return None
    inc["diagnosis"] = diagnosis
    logger.info("Incident %s: diagnosis attached (type=%s)", incident_id, diagnosis.get("incident_type"))
    return inc


def set_plan(incident_id: str, plan: dict) -> Optional[dict]:
    inc = _incidents.get(incident_id)
    if inc is None:
        logger.warning("set_plan: unknown incident '%s'", incident_id)
        return None
    inc["plan"] = plan
    # Propagate v1 compat fields from the plan's first step + script
    steps = plan.get("steps", [])
    if steps:
        inc["action"] = steps[0].get("action")
        inc["target"] = steps[0].get("target")
    inc["script"] = plan.get("script")
    logger.info("Incident %s: plan attached (%d steps)", incident_id, len(steps))
    return inc


def set_status(incident_id: str, status: str) -> Optional[dict]:
    inc = _incidents.get(incident_id)
    if inc is None:
        logger.warning("set_status: unknown incident '%s'", incident_id)
        return None
    old = inc["status"]
    inc["status"] = status
    logger.info("Incident %s: status %s → %s", incident_id, old, status)
    return inc


def add_attempt(incident_id: str, attempt: dict) -> Optional[dict]:
    inc = _incidents.get(incident_id)
    if inc is None:
        logger.warning("add_attempt: unknown incident '%s'", incident_id)
        return None
    inc["attempts"].append(attempt)
    logger.info(
        "Incident %s: attempt added (action=%s, result=%s, actor=%s)",
        incident_id,
        attempt.get("action"),
        attempt.get("result"),
        attempt.get("actor"),
    )
    return inc


def assign_engineer(incident_id: str, engineer: dict) -> Optional[dict]:
    inc = _incidents.get(incident_id)
    if inc is None:
        logger.warning("assign_engineer: unknown incident '%s'", incident_id)
        return None
    inc["assigned_engineer"] = engineer
    logger.info("Incident %s: assigned to engineer '%s'", incident_id, engineer.get("id"))
    return inc


def set_decision(incident_id: str, decision: str) -> Optional[dict]:
    inc = _incidents.get(incident_id)
    if inc is None:
        logger.warning("set_decision: unknown incident '%s'", incident_id)
        return None
    inc["decision"] = decision
    logger.info("Incident %s: decision = %s", incident_id, decision)
    return inc


# ---------------------------------------------------------------------------
# v1 backward-compat alias (still called by routes/execute.py)
# ---------------------------------------------------------------------------

def resolve_incident(incident_id: str, decision: str) -> Optional[dict]:
    """Set decision and flip status to resolved.  v1 compat; callers may
    continue using this instead of set_decision + set_status separately."""
    inc = set_decision(incident_id, decision)
    if inc is None:
        return None
    return set_status(incident_id, "resolved")


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def get_incident(incident_id: str) -> Optional[dict]:
    return _incidents.get(incident_id)
