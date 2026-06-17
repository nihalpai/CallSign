"""
Brain pipeline — public entry point.

run_brain(alert, log) -> (diagnosis, plan)

Runs diagnostician → strategist. On any exception falls back to the full
deterministic engine and emits a [SYSTEM] warning via log.
"""
from __future__ import annotations

from typing import Callable

from app.logging_config import get_logger

logger = get_logger(__name__)


def run_brain(
    alert: dict,
    log: Callable[[str, str], None],
    session_id: str | None = None,
) -> tuple[dict, dict]:
    """
    Orchestrate the two-agent pipeline.

    Args:
        alert: Raw alert dict matching data-contracts §1.
        log:   Callback (source: str, message: str) → each call becomes an SSE log.

    Returns:
        (diagnosis, plan) matching data-contracts §3 and §4.
    """
    if session_id is None:
        import uuid
        session_id = f"{alert.get('alert_id', 'inc')}-{uuid.uuid4().hex[:8]}"

    log("AGENT", f"Diagnosing alert {alert.get('alert_id', '?')} — priority {alert.get('priority', '?')}")

    try:
        from app.brain.diagnostician import diagnostician
        from app.brain.strategist import strategist

        diagnosis = diagnostician(alert, log, session_id)
        log(
            "AGENT",
            f"{diagnosis['incident_type']} on {diagnosis['affected_service']} "
            f"@ {diagnosis['exact_location'].get('route', '/')}; runbook {diagnosis['runbook']}",
        )

        plan = strategist(diagnosis, log, session_id)
        log("AGENT", f"Planned {len(plan['steps'])} step(s); first = {plan['steps'][0]['action']}.")

        return diagnosis, plan

    except Exception as exc:
        logger.exception("Brain pipeline failed — engaging full deterministic fallback")
        log("AGENT", f"[SYSTEM] Brain error ({type(exc).__name__}) — switching to deterministic fallback.")

        from app.brain.fallback import run_fallback
        diagnosis, plan = run_fallback(alert, log)
        log(
            "AGENT",
            f"[Fallback] {diagnosis['incident_type']} on {diagnosis['affected_service']}; "
            f"runbook {diagnosis['runbook']}",
        )
        return diagnosis, plan
