"""
Escalation orchestration (data-contracts §8).

select_approver(area, now) -> dict | None
    When EXPERTISE_ROUTING is True and area is given, finds the first available
    engineer whose owns list matches area; falls back to select_engineer().
    Otherwise delegates directly to select_engineer().

select_engineer(now) -> dict | None
    Reads ON_CALL_PATH; finds the first active engineer in their shift.
    Fallback: first active engineer regardless of shift.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, time as dtime
from zoneinfo import ZoneInfo
from typing import Callable, Optional

from app.config import ON_CALL_PATH, EXPERTISE_ROUTING
from app import events
from app.logging_config import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Expertise routing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _area_matches(area: str, owns: list[str]) -> bool:
    """Return True if area matches any entry in the owns list (case-insensitive substring)."""
    area_lower = area.lower()
    for owned in owns:
        owned_lower = owned.lower()
        if owned_lower in area_lower or area_lower in owned_lower:
            return True
    return False


def _awake_and_available(eng: dict, now: datetime) -> bool:
    if eng.get("status") != "active":
        return False
    tz = ZoneInfo(eng["timezone"])
    local_now = now.astimezone(tz)
    return _in_shift(local_now, eng["shift_start"], eng["shift_end"])


def select_approver(area: Optional[str] = None, now: Optional[datetime] = None) -> Optional[dict]:
    """Select the most appropriate approver for area.

    When EXPERTISE_ROUTING is True and area is given:
        1. Find the first available engineer whose owns list matches area.
        2. Fall back to select_engineer() if no matching-and-available owner found.
    Otherwise: delegate directly to select_engineer().
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not EXPERTISE_ROUTING or not area:
        return select_engineer(now)

    engineers = _load_engineers()
    for eng in engineers:
        owns = eng.get("owns") or []
        if _area_matches(area, owns) and _awake_and_available(eng, now):
            logger.info("[SYSTEM] Routing to %s — owns %s", eng.get("name"), area)
            return eng

    logger.info("[SYSTEM] no owner for %s — using on-call rule", area)
    return select_engineer(now)


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
        return s <= t < e
    # Wraps midnight
    return t >= s or t < e


def _load_engineers() -> list[dict]:
    try:
        with open(ON_CALL_PATH) as f:
            data = json.load(f)
        return data.get("engineers", [])
    except Exception:
        logger.exception("Failed to load on-call registry from %s", ON_CALL_PATH)
        return []


def select_engineer(now: Optional[datetime] = None) -> Optional[dict]:
    """Select the on-call engineer.

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

    fallback = active[0]
    logger.warning("[SYSTEM] off-hours — paging %s anyway", fallback.get("name"))
    return fallback
