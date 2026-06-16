from __future__ import annotations
from fastapi import APIRouter
from app.models import Alert, TriggerResponse
from app.state import set_status
from app.incidents import open_incident
from app.events import emit_log, emit_incident

router = APIRouter()


@router.post("/webhook/trigger", response_model=TriggerResponse)
async def trigger(alert: Alert) -> TriggerResponse:
    alert_dict = alert.model_dump()

    def log(source: str, message: str) -> None:
        emit_log(source, message)

    log("SYSTEM", f"Alert received: {alert.title}")

    # Mark the compromised host
    set_status(alert.host, "compromised")

    # Run the brain — lazy import so the server boots without the brain module
    try:
        from app.brain.pipeline import run_brain
        forensic, commander = run_brain(alert_dict, log)
    except Exception as e:
        log("SYSTEM", f"Brain unavailable ({e}); using fallback script")
        forensic = {
            "severity": "SEV-1",
            "cve": "CVE-2026-1337",
            "vulnerable_server": alert.host,
            "service": "Authentication",
            "blast_radius": [],
            "runbook": "CVE-2026-Shellshock-Mitigation.md",
            "recommended_action": "isolate_container",
            "action_target": alert.host,
            "rationale": "fallback",
        }
        commander = {
            "script": (
                f"Severity one alert on {alert.host}. "
                "The runbook recommends immediate container isolation. "
                "Do you approve isolating it?"
            ),
            "action": "isolate_container",
            "target": alert.host,
        }

    inc = open_incident(
        action=commander["action"],
        target=commander["target"],
        script=commander["script"],
    )
    emit_incident(inc)

    return TriggerResponse(incident_id=inc["incident_id"])
