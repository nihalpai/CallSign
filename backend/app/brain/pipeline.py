"""
Brain pipeline — public entry point for the backend.

run_brain(alert, log) -> (forensic, commander)

Selects the Lyzr Automata path when LYZR_API_KEY is set and the SDK is installed;
falls back to the deterministic local implementation otherwise.
"""

import logging
import os
from typing import Callable

_log = logging.getLogger(__name__)


def run_brain(
    alert: dict,
    log: Callable[[str, str], None],
) -> tuple[dict, dict]:
    """
    Orchestrate the two-agent pipeline.

    Args:
        alert:  Raw alert dict matching data-contracts §1.
        log:    Callback with signature (source: str, message: str).
                Each call becomes a "AGENT" SSE log event.

    Returns:
        (forensic, commander) matching data-contracts §3 and §4.
    """
    log("AGENT", f"Parsing alert {alert.get('alert_id', '?')} — priority {alert.get('priority', '?')}")

    api_key: str | None = os.getenv("LYZR_API_KEY")

    if api_key:
        try:
            forensic, commander = _run_lyzr(alert, log)
            log(
                "AGENT",
                f"Matched runbook {forensic['runbook']}; "
                f"recommending {forensic['recommended_action']} on {forensic['action_target']}",
            )
            log("AGENT", "Drafted approval script.")
            return forensic, commander
        except Exception as exc:
            _log.warning("Lyzr path failed (%s) — falling back to deterministic engine.", exc)
            log("AGENT", f"[WARN] Lyzr agent error ({type(exc).__name__}) — switching to fallback.")

    # Deterministic fallback (no network, always works)
    from .fallback import run_fallback

    forensic, commander = run_fallback(alert, log)
    log(
        "AGENT",
        f"Matched runbook {forensic['runbook']}; "
        f"recommending {forensic['recommended_action']} on {forensic['action_target']}",
    )
    log("AGENT", "Drafted approval script.")
    return forensic, commander


# ---------------------------------------------------------------------------
# Lyzr Automata path (imported lazily — missing SDK never breaks fallback)
# ---------------------------------------------------------------------------

def _run_lyzr(
    alert: dict,
    log: Callable[[str, str], None],
) -> tuple[dict, dict]:
    """
    Runs the two-agent Lyzr pipeline.  Any exception propagates to run_brain,
    which then activates the fallback.
    """
    from .forensic import run_forensic
    from .commander import run_commander

    forensic = run_forensic(alert, log)
    commander = run_commander(forensic, log)
    return forensic, commander
