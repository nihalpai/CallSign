"""
Escalation orchestration (data-contracts §8, escalation.md).

select_engineer(now=None) -> dict | None
    Reads ON_CALL_PATH; finds the first "active" engineer whose local time
    falls within [shift_start, shift_end) (handles midnight wrap).
    Fallback: first active engineer regardless of shift.

escalate(incident, log) -> None
    Sets status → "escalated" then "awaiting_approval", assigns the selected
    engineer, emits the incident, and fans out to Slack + voice per toggles.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, time as dtime
from zoneinfo import ZoneInfo
from typing import Callable

from app.config import (
    ON_CALL_PATH,
    SLACK_ENABLED,
    VOICE_ENABLED,
    LYZR_VOICE_AGENT_ID,
)
from app import incidents, events
from app.logging_config import get_logger

logger = get_logger(__name__)


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _in_shift(local_now: datetime, shift_start: str, shift_end: str) -> bool:
    """Return True if local_now's time is in [shift_start, shift_end).

    Handles midnight wrap: when shift_end <= shift_start the window crosses
    midnight (e.g. 21:00 → 09:00).
    """
    t = local_now.time().replace(second=0, microsecond=0)
    s = _parse_hhmm(shift_start)
    e = _parse_hhmm(shift_end)

    if s < e:
        # Normal window: 09:00 – 21:00
        return s <= t < e
    # Wraps midnight: 21:00 – 09:00  →  t >= 21:00 OR t < 09:00
    return t >= s or t < e


def _load_engineers() -> list[dict]:
    try:
        with open(ON_CALL_PATH) as f:
            data = json.load(f)
        return data.get("engineers", [])
    except Exception:
        logger.exception("Failed to load on-call registry from %s", ON_CALL_PATH)
        return []


def select_engineer(now: datetime | None = None) -> dict | None:
    """Select the on-call engineer.

    `now` is UTC; defaults to datetime.now(utc). Injectable for tests.
    Returns the first engineer whose shift contains their current local time,
    or the first active engineer as a fallback.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    engineers = _load_engineers()
    active = [e for e in engineers if e.get("status") == "active"]
    if not active:
        return None

    for eng in active:
        tz = ZoneInfo(eng["timezone"])
        local_now = now.astimezone(tz)
        if _in_shift(local_now, eng["shift_start"], eng["shift_end"]):
            return eng

    # Fallback: nobody is in their shift — page the first active engineer
    fallback = active[0]
    logger.warning(
        "[SYSTEM] off-hours — paging %s anyway", fallback.get("name")
    )
    return fallback


def _trigger_voice(engineer: dict, incident: dict, log: Callable[[str, str], None]) -> None:
    """Log a voice call; fires the Lyzr voice agent when credentials exist."""
    phone = engineer.get("phone", "<unknown>")
    name = engineer.get("name", "<unknown>")
    script = (incident.get("plan") or {}).get("script", "")
    log("VOICE", f"Calling {name} ({phone}) — reading approval script")
    logger.info("[VOICE] would call %s with script: %s", phone, script)

    if not VOICE_ENABLED or not LYZR_VOICE_AGENT_ID:
        return

    try:
        from app.integrations import lyzr as lyzr_client
        session_id = incident.get("incident_id", "voice-session")
        lyzr_client.call_agent(LYZR_VOICE_AGENT_ID, script, session_id)
    except Exception:
        logger.exception("[VOICE] Lyzr voice call failed for incident %s", incident.get("incident_id"))


def escalate(incident: dict, log: Callable[[str, str], None]) -> None:
    """Orchestrate escalation for `incident`.

    1. Select the on-call engineer.
    2. Log, assign, set status → escalated → awaiting_approval, emit.
    3. Fan out to Slack + voice per toggles (failures are logged, not raised).
    """
    from app.integrations import slack as slack_module

    engineer = select_engineer()

    if engineer is None:
        log("SYSTEM", "No active engineers in on-call registry — escalation skipped")
        logger.error("escalate: no active engineers found")
        return

    # Build local time string for the log message
    tz = ZoneInfo(engineer["timezone"])
    local_now = datetime.now(timezone.utc).astimezone(tz)
    local_time_str = local_now.strftime("%H:%M")
    name = engineer.get("name", "unknown")

    log("SYSTEM", f"Escalating to {name} (local {local_time_str})")
    logger.info("[SYSTEM] Escalating to %s (local %s)", name, local_time_str)

    inc_id = incident["incident_id"]

    incidents.assign_engineer(inc_id, {
        "id": engineer["id"],
        "name": engineer["name"],
        "channels": _active_channels(),
    })
    incidents.set_status(inc_id, "escalated")
    incidents.set_status(inc_id, "awaiting_approval")

    updated = incidents.get_incident(inc_id)
    if updated:
        events.emit_incident(updated)

    # Slack fan-out (self-disabling when SLACK_ENABLED is False)
    try:
        slack_module.post_incident(engineer, incident, log)
    except Exception:
        logger.exception("Slack fan-out failed for incident %s", inc_id)

    # Voice fan-out
    try:
        _trigger_voice(engineer, incident, log)
    except Exception:
        logger.exception("Voice fan-out failed for incident %s", inc_id)


def _active_channels() -> list[str]:
    channels = []
    if SLACK_ENABLED:
        channels.append("slack")
    if VOICE_ENABLED:
        channels.append("voice")
    if not channels:
        channels.append("ui")
    return channels
