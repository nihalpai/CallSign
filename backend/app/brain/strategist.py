"""
Agent 2 — Strategist.

strategist(diagnosis, log) -> dict (§4 Plan)

Calls the Lyzr Studio Strategist agent when LYZR_API_KEY and
LYZR_STRATEGIST_AGENT_ID are set. Falls back to plan_fallback otherwise
or on any error.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from app.logging_config import get_logger

logger = get_logger(__name__)

_VALID_ACTIONS = {
    "rollback_deployment", "restart_service", "isolate_service", "scale_up",
    "disable_feature", "isolate_container", "quarantine_host", "revoke_keys",
}
_REQUIRED_KEYS = {"summary", "steps", "script"}
_JSON_ONLY_NUDGE = "\n\nReturn ONLY the JSON object. No explanation, no markdown fences."
MAX_SENTENCES = 3


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
    if not isinstance(obj.get("steps"), list) or not obj["steps"]:
        return False
    for step in obj["steps"]:
        if not isinstance(step, dict):
            return False
        if step.get("action") not in _VALID_ACTIONS:
            return False
        if step.get("autonomy") not in {"auto", "human"}:
            return False
    if not isinstance(obj.get("script"), str) or not obj["script"].strip():
        return False
    return True


def _sentence_count(text: str) -> int:
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return len([p for p in parts if p])


def _truncate_script(script: str) -> str:
    parts = [p for p in re.split(r"(?<=[.?!])\s+", script.strip()) if p]
    if len(parts) <= MAX_SENTENCES:
        return script
    kept = parts[:MAX_SENTENCES - 1] + [parts[-1]]
    return " ".join(kept)


def _enforce_script_rules(obj: dict, log: Callable[[str, str], None]) -> dict:
    script: str = obj["script"]
    count = _sentence_count(script)
    if count > MAX_SENTENCES:
        logger.warning("Strategist script: %d sentences — truncating to %d", count, MAX_SENTENCES)
        log("AGENT", f"[WARN] Script was {count} sentences — truncated to {MAX_SENTENCES}.")
        obj = {**obj, "script": _truncate_script(script)}
    return obj


def _build_message(diagnosis: dict) -> str:
    return json.dumps(diagnosis, indent=2)


def strategist(diagnosis: dict, log: Callable[[str, str], None], session_id: str | None = None) -> dict:
    """
    Produce a §4 Plan dict. Falls back deterministically on any failure.
    """
    from app.config import LYZR_API_KEY, LYZR_STRATEGIST_AGENT_ID

    if LYZR_API_KEY and LYZR_STRATEGIST_AGENT_ID:
        try:
            return _call_lyzr(diagnosis, log, LYZR_STRATEGIST_AGENT_ID, session_id)
        except Exception:
            logger.exception("Strategist: Lyzr path failed — falling back")
            log("AGENT", "[SYSTEM] Lyzr Strategist unavailable — switching to deterministic fallback.")

    from app.brain.fallback import plan_fallback
    return plan_fallback(diagnosis)


def _call_lyzr(diagnosis: dict, log: Callable[[str, str], None], agent_id: str, session_id: str | None = None) -> dict:
    from app.integrations.lyzr import call_agent
    import uuid

    message = _build_message(diagnosis)
    # Unique session per incident — never reuse affected_service (constant), which
    # would pile every run on that service into one ever-growing Lyzr conversation.
    session_id = session_id or f"strat-{uuid.uuid4().hex[:8]}"

    log("AGENT", "Strategist: sending diagnosis to Lyzr Studio…")
    raw = call_agent(agent_id, message, session_id)
    obj = _parse_json(raw)

    if obj is None or not _validate(obj):
        log("AGENT", "Strategist: JSON parse failed — retrying with nudge…")
        raw2 = call_agent(agent_id, message + _JSON_ONLY_NUDGE, session_id)
        obj = _parse_json(raw2)

    if obj is None or not _validate(obj):
        raise ValueError(f"Strategist returned unparseable output after retry: {raw!r}")

    return _enforce_script_rules(obj, log)
