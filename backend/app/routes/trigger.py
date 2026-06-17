"""POST /webhook/trigger — alert intake, brain, and auto-remediation phase.

Accepts:
    - An internal Alert (§1) body — used directly.
    - A raw Datadog webhook payload (§1b) — mapped via map_datadog_payload.

Flow (non-blocking; returns incident_id immediately):
    1. Detect payload type → normalize to §1 Alert.
    2. Emit log, open incident, emit incident.
    3. Run brain → diagnosis + plan; attach to incident; emit incident.
    4. Mark affected service compromised/degraded per incident_type.
    5. Run auto-remediation phase (resolves or escalates; emits throughout).
    6. Return {"incident_id": ...}.
"""
from __future__ import annotations

from fastapi import APIRouter
from app.models import TriggerResponse
from app.config import EXECUTION_MODE
from app.events import emit_log, emit_incident
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Required fields for an internal §1 Alert.
_ALERT_REQUIRED = {"alert_id", "title", "alert_type", "priority", "tags", "body", "host", "timestamp"}


def _is_internal_alert(raw: dict) -> bool:
    """Return True when the payload already looks like a §1 Alert."""
    return _ALERT_REQUIRED.issubset(raw.keys())


@router.post("/webhook/trigger", response_model=TriggerResponse)
async def trigger(raw: dict) -> TriggerResponse:
    def log(source: str, message: str) -> None:
        emit_log(source, message)

    # --- 1. Normalise to §1 Alert ---
    try:
        if _is_internal_alert(raw):
            alert = raw
        else:
            from app.integrations.datadog import map_datadog_payload
            alert = map_datadog_payload(raw)
    except Exception:
        logger.exception("trigger: failed to parse alert payload")
        log("SYSTEM", "Alert payload could not be parsed — using raw body as-is")
        alert = raw

    log("SYSTEM", f"Alert received: {alert.get('title', '(no title)')}")

    # --- 2. Open incident ---
    from app.incidents import open_incident, set_diagnosis, set_plan, set_status as inc_set_status
    inc = open_incident(alert, EXECUTION_MODE)
    inc_id = inc["incident_id"]
    emit_incident(inc)

    # --- 3. Run brain (session_id = incident_id → each incident gets its own
    #         clean, single-turn Lyzr session; no cross-incident accumulation) ---
    diagnosis: dict = {}
    plan: dict = {}
    try:
        from app.brain.pipeline import run_brain
        diagnosis, plan = run_brain(alert, log, session_id=inc_id)
    except Exception as exc:
        logger.exception("trigger: brain raised — engaging static fallback")
        log("SYSTEM", f"Brain unavailable ({exc}) — using static fallback")
        try:
            from app.brain.fallback import run_fallback
            diagnosis, plan = run_fallback(alert, log)
        except Exception:
            logger.exception("trigger: static fallback also raised")
            host = alert.get("host", "unknown")
            diagnosis = {
                "incident_type": "security",
                "severity": "SEV-1",
                "affected_service": host,
                "exact_location": {"service": host, "route": "/", "deploy_id": "", "commit": "", "datadog_link": ""},
                "blast_radius": [],
                "runbook": "CVE-2026-Shellshock-Mitigation.md",
                "confidence": 0.5,
                "summary": "Fallback diagnosis",
                "rationale": "Brain unavailable",
                "cve": None,
            }
            plan = {
                "summary": "Isolate container immediately.",
                "steps": [{"action": "isolate_container", "target": host, "autonomy": "human", "reversible": True, "description": "Sever container network"}],
                "script": f"Severity one alert on {host}. The runbook recommends immediate container isolation. Do you approve isolating it?",
            }

    inc_id = inc["incident_id"]
    set_diagnosis(inc_id, diagnosis)
    set_plan(inc_id, plan)
    from app.incidents import get_incident
    inc = get_incident(inc_id)
    emit_incident(inc)

    # --- 4. Mark affected service ---
    affected = diagnosis.get("affected_service") or alert.get("host", "")
    if affected:
        from app.state import set_status as state_set_status
        incident_type = diagnosis.get("incident_type", "")
        new_status = "compromised" if incident_type == "security" else "degraded"
        state_set_status(affected, new_status)

    # --- 5. Auto-remediation phase ---
    try:
        from app.remediation.engine import run_auto_remediation
        inc = get_incident(inc_id)
        run_auto_remediation(inc, alert, log)
    except Exception:
        logger.exception("trigger: run_auto_remediation raised for incident %s", inc_id)
        log("SYSTEM", f"Remediation engine error for incident {inc_id} — incident left in current state")

    return TriggerResponse(incident_id=inc_id)
