"""
Agent 1 — Diagnostician.

diagnostician(alert, log) -> dict (§3 Diagnosis)

Calls the Lyzr Studio Diagnostician agent when LYZR_API_KEY and
LYZR_DIAGNOSTICIAN_AGENT_ID are set. Falls back to diagnose_fallback otherwise
or on any error.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from app.logging_config import get_logger

logger = get_logger(__name__)

# §3 required keys
_REQUIRED_KEYS = {
    "incident_type", "severity", "affected_service", "exact_location",
    "blast_radius", "runbook", "confidence", "summary", "rationale",
}
_VALID_INCIDENT_TYPES = {
    "security", "bad_deploy", "error_spike", "latency", "crash_loop", "resource_exhaustion",
}
_JSON_ONLY_NUDGE = "\n\nReturn ONLY the JSON object. No explanation, no markdown fences."


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        return match.group(1).strip()
    return raw


def _parse_json(raw: str) -> dict | None:
    cleaned = _strip_fences(raw)
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return None


def _validate(obj: dict) -> bool:
    if not _REQUIRED_KEYS.issubset(obj.keys()):
        return False
    if obj.get("incident_type") not in _VALID_INCIDENT_TYPES:
        return False
    if not isinstance(obj.get("blast_radius"), list):
        return False
    if not isinstance(obj.get("exact_location"), dict):
        return False
    return True


def _build_message(alert: dict) -> str:
    from app.state import get_state, blast_radius
    from app.deployments import get_deployment

    state = get_state()
    # Compact service map: id + depended_on_by only
    service_map = [
        {"id": s["id"], "service": s.get("service", ""), "depended_on_by": s.get("depended_on_by", [])}
        for s in state.get("servers", [])
    ]

    # Extract service from tags for deployment lookup
    tag_map: dict[str, str] = {}
    for tag in alert.get("tags", []):
        if ":" in tag:
            k, _, v = tag.partition(":")
            tag_map[k.lower()] = v

    service_id = tag_map.get("service") or alert.get("host", "")
    deployment = get_deployment(service_id)

    payload = {
        "alert": alert,
        "service_map": service_map,
        "deployment": deployment,
    }
    return json.dumps(payload, indent=2)


def diagnostician(alert: dict, log: Callable[[str, str], None], session_id: str | None = None) -> dict:
    """
    Produce a §3 Diagnosis dict. Falls back deterministically on any failure.
    """
    from app.config import LYZR_API_KEY, LYZR_DIAGNOSTICIAN_AGENT_ID

    if LYZR_API_KEY and LYZR_DIAGNOSTICIAN_AGENT_ID:
        try:
            return _call_lyzr(alert, log, LYZR_DIAGNOSTICIAN_AGENT_ID, session_id)
        except Exception:
            logger.exception("Diagnostician: Lyzr path failed — falling back")
            log("AGENT", "[SYSTEM] Lyzr Diagnostician unavailable — switching to deterministic fallback.")

    from app.brain.fallback import diagnose_fallback
    return diagnose_fallback(alert)


def _call_lyzr(alert: dict, log: Callable[[str, str], None], agent_id: str, session_id: str | None = None) -> dict:
    from app.integrations.lyzr import call_agent
    import uuid

    message = _build_message(alert)
    # Unique session per incident — never reuse alert_id (constant for canned
    # alerts), which would pile every run into one ever-growing Lyzr conversation.
    session_id = session_id or f"diag-{uuid.uuid4().hex[:8]}"

    log("AGENT", "Diagnostician: sending alert to Lyzr Studio…")
    raw = call_agent(agent_id, message, session_id)
    obj = _parse_json(raw)

    if obj is None or not _validate(obj):
        log("AGENT", "Diagnostician: JSON parse failed — retrying with nudge…")
        raw2 = call_agent(agent_id, message + _JSON_ONLY_NUDGE, session_id)
        obj = _parse_json(raw2)

    if obj is None or not _validate(obj):
        raise ValueError(f"Diagnostician returned unparseable output after retry: {raw!r}")

    return obj
