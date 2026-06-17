"""
Remediation engine — policy loop (remediation.md §Autonomy policy).

Two public functions:
    run_auto_remediation(incident, alert, log) -> None
        Auto phase: severity gate → walk plan auto-steps → verify → resolve or escalate.

    execute_step(incident, action, target, actor, log) -> dict
        Run ONE approved action (from a human-approved /execute call or the auto loop).
        Updates attempts/state/incident status; returns updated incident.

`log` callable signature: log(source: str, message: str) -> None
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.logging_config import get_logger
from app.remediation.executor import get_executor

logger = get_logger(__name__)

_LOG_SOURCE = "REMEDIATION"

# Severity ordering: lower index = higher severity (SEV-1 is most severe)
_SEV_ORDER = ["SEV-1", "SEV-2", "SEV-3", "SEV-4", "SEV-5"]


def _sev_value(sev: str) -> int:
    """Return a comparable integer for severity: lower = more severe."""
    try:
        return _SEV_ORDER.index(sev)
    except ValueError:
        return len(_SEV_ORDER)  # unknown → least severe, never gate


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Auto-remediation phase
# ---------------------------------------------------------------------------

def run_auto_remediation(incident: dict, alert: dict, log: Callable[[str, str], None]) -> None:
    """Auto phase: severity gate, walk plan auto-steps, run+verify, resolve or escalate.

    Called from routes/trigger.py after the brain attaches diagnosis + plan.
    Never raises — all exceptions are caught and logged; on failure escalate.
    """
    from app import incidents as inc_store, events
    from app.config import AUTO_REMEDIATE, AUTO_REMEDIATE_MAX_SEVERITY

    inc_id = incident["incident_id"]

    # Severity gate
    diagnosis = incident.get("diagnosis") or {}
    severity = diagnosis.get("severity", "SEV-3")
    cap = AUTO_REMEDIATE_MAX_SEVERITY  # e.g. "SEV-2"

    if not AUTO_REMEDIATE:
        log(_LOG_SOURCE, f"AUTO_REMEDIATE=false — escalating incident {inc_id}")
        _do_escalate(incident, log)
        return

    # Escalate only when severity is STRICTLY more severe than the cap.
    # e.g. cap=SEV-2: SEV-1 (index 0) < SEV-2 (index 1) → escalate;
    #                 SEV-2 (index 1) < SEV-2 (index 1) → False → auto-run.
    if _sev_value(severity) < _sev_value(cap):
        log(
            _LOG_SOURCE,
            f"Severity {severity} exceeds cap {cap} — skipping auto, escalating",
        )
        _do_escalate(incident, log)
        return

    plan = incident.get("plan") or {}
    steps = plan.get("steps", [])

    executor = get_executor()

    for step in steps:
        autonomy = step.get("autonomy")
        action = step.get("action")
        target = step.get("target")

        if autonomy == "human":
            log(
                _LOG_SOURCE,
                f"Step '{action}' on {target} requires human approval — escalating",
            )
            _do_escalate(incident, log)
            return

        if autonomy != "auto":
            log(_LOG_SOURCE, f"Unknown autonomy '{autonomy}' on step '{action}' — escalating")
            _do_escalate(incident, log)
            return

        # Run auto step
        log(_LOG_SOURCE, f"Auto-remediating: {action} on {target}…")
        inc_store.set_status(inc_id, "remediating")
        # Re-fetch so we always have the latest incident object
        incident = inc_store.get_incident(inc_id)
        events.emit_incident(incident)

        result_dict = {"ok": False, "detail": "executor not called"}
        try:
            result_dict = executor.run(action, target)
        except Exception:
            logger.exception("executor.run raised for action=%s target=%s", action, target)
            result_dict = {"ok": False, "detail": "executor raised unexpectedly"}

        result_str = "succeeded" if result_dict.get("ok") else "failed"
        attempt = {
            "action": action,
            "target": target,
            "actor": "auto",
            "result": result_str,
            "ts": _now_iso(),
        }
        inc_store.add_attempt(inc_id, attempt)
        incident = inc_store.get_incident(inc_id)

        log(_LOG_SOURCE, f"{action} on {target}: {result_str} — {result_dict.get('detail', '')}")
        events.emit_state()
        events.emit_log(_LOG_SOURCE, f"Attempt recorded: {action}/{target} → {result_str}")
        events.emit_incident(incident)

        # Verify
        inc_store.set_status(inc_id, "verifying")
        incident = inc_store.get_incident(inc_id)
        events.emit_incident(incident)

        cleared = False
        try:
            cleared = executor.verify(incident, alert)
        except Exception:
            logger.exception("executor.verify raised")

        if cleared:
            inc_store.set_status(inc_id, "resolved")
            incident = inc_store.get_incident(inc_id)
            events.emit_incident(incident)
            log(_LOG_SOURCE, f"Incident {inc_id} auto-resolved after {action} on {target}")
            events.emit_log(_LOG_SOURCE, f"[auto-resolved] {action} cleared the alert on {target}")
            return

        log(_LOG_SOURCE, f"Alert not yet cleared after {action} — continuing plan")

    # Exhausted all auto steps without resolving
    log(_LOG_SOURCE, f"Auto steps exhausted for {inc_id} — escalating")
    _do_escalate(incident, log)


def _do_escalate(incident: dict, log: Callable[[str, str], None]) -> None:
    """Set status to escalated, emit, then call the escalation module."""
    from app import incidents as inc_store, events

    inc_id = incident["incident_id"]
    inc_store.set_status(inc_id, "escalated")
    incident = inc_store.get_incident(inc_id)
    events.emit_incident(incident)
    log(_LOG_SOURCE, f"Incident {inc_id} escalated")

    try:
        from app.escalation import escalate
        escalate(incident, log)
    except Exception:
        logger.exception("escalation.escalate raised for incident %s", inc_id)
        log(_LOG_SOURCE, f"Escalation module error for {inc_id} — incident remains escalated")


# ---------------------------------------------------------------------------
# Single-step execution (human-approved or actor-supplied)
# ---------------------------------------------------------------------------

def execute_step(
    incident: dict,
    action: str,
    target: str,
    actor: str,
    log: Callable[[str, str], None],
) -> dict:
    """Run ONE approved action via the executor.

    - If the incident is already resolved: no-op + WARNING log, return incident unchanged.
    - On success: incident status → resolved; decision → approve.
    - On failure: attempt recorded with result=failed; status unchanged (caller decides).
    - Always: appends attempt, emits state + log + incident SSE.
    """
    from app import incidents as inc_store, events

    inc_id = incident["incident_id"]
    current_status = incident.get("status")

    # Idempotency guard
    if current_status == "resolved":
        logger.warning(
            "execute_step called on already-resolved incident %s — no-op", inc_id
        )
        log(_LOG_SOURCE, f"[WARN] Incident {inc_id} already resolved — execute_step no-op")
        return incident

    log(_LOG_SOURCE, f"Executing step: {action} on {target} (actor={actor})")

    executor = get_executor()
    result_dict = {"ok": False, "detail": "executor not called"}
    try:
        result_dict = executor.run(action, target)
    except Exception:
        logger.exception("executor.run raised in execute_step action=%s target=%s", action, target)
        result_dict = {"ok": False, "detail": "executor raised unexpectedly"}

    result_str = "succeeded" if result_dict.get("ok") else "failed"
    attempt = {
        "action": action,
        "target": target,
        "actor": actor,
        "result": result_str,
        "ts": _now_iso(),
    }
    inc_store.add_attempt(inc_id, attempt)
    incident = inc_store.get_incident(inc_id)

    events.emit_state()
    log(_LOG_SOURCE, f"{action} on {target}: {result_str} — {result_dict.get('detail', '')}")
    events.emit_log(_LOG_SOURCE, f"Step executed: {action}/{target} → {result_str} by {actor}")

    if result_dict.get("ok"):
        inc_store.set_decision(inc_id, "approve")
        inc_store.set_status(inc_id, "resolved")
        incident = inc_store.get_incident(inc_id)
        events.emit_incident(incident)
        log(_LOG_SOURCE, f"Incident {inc_id} resolved after {action}")
    else:
        incident = inc_store.get_incident(inc_id)
        events.emit_incident(incident)
        log(_LOG_SOURCE, f"Action {action} failed on {target} — incident remains {incident['status']}")

    return incident
