"""
Datadog webhook → internal Alert mapper (data-contracts §1b).

map_datadog_payload(raw: dict) -> dict

This is the ONLY Datadog-aware code in the codebase.
Everything downstream receives the §1 internal Alert shape.

Mapping rules (§1b):
  $ID             → alert_id       (str)
  $EVENT_TITLE    → title          (str)
  $PRIORITY       → priority       ("P1"…"P5"; missing/blank → "P3")
  $TAGS           → tags           (comma string → list; strip whitespace)
  $EVENT_MSG      → body           (str)
  $HOSTNAME       → host           (falls back to host:/service: tag if blank)
  $DATE           → timestamp      (normalized to ISO-8601 UTC string)
  alert_type      → always "reliability" (Datadog webhook; security alerts use §1 directly)

Unknown/extra fields are silently ignored.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.logging_config import get_logger

logger = get_logger(__name__)

_PRIORITY_PATTERN = re.compile(r"^P[1-5]$")


def _normalize_priority(raw: str | None) -> str:
    if not raw:
        return "P3"
    p = raw.strip()
    if _PRIORITY_PATTERN.match(p):
        return p
    return "P3"


def _parse_tags(raw_tags: str | list | None) -> list[str]:
    """Accept a comma-delimited string OR an already-split list."""
    if raw_tags is None:
        return []
    if isinstance(raw_tags, list):
        return [t.strip() for t in raw_tags if t.strip()]
    # Comma-separated string from the $TAGS template variable
    return [t.strip() for t in str(raw_tags).split(",") if t.strip()]


def _host_from_tags(tags: list[str]) -> str | None:
    """Extract the first host: or service: tag value as a fallback host."""
    for prefix in ("host:", "service:"):
        for tag in tags:
            if tag.startswith(prefix):
                return tag[len(prefix):]
    return None


def _normalize_timestamp(raw: str | None) -> str:
    """Return an ISO-8601 UTC string, or the current time if parsing fails."""
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        # Datadog $DATE may be an epoch ms integer as a string, or an ISO string
        epoch_ms = int(raw)
        dt = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        pass
    try:
        # Try ISO-8601 parse (with or without Z / offset)
        raw_clean = raw.strip()
        if raw_clean.endswith("Z"):
            raw_clean = raw_clean[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        logger.warning("map_datadog_payload: could not parse timestamp %r; using now", raw)
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def map_datadog_payload(raw: dict) -> dict:
    """Map a raw Datadog webhook body to an internal Alert (§1).

    Tolerates missing fields. Never raises.
    """
    tags = _parse_tags(raw.get("tags"))
    host_raw = raw.get("host") or raw.get("$HOSTNAME") or ""
    host = host_raw.strip() or _host_from_tags(tags) or "unknown"

    alert: dict = {
        "alert_id": str(raw.get("alert_id") or raw.get("$ID") or ""),
        "title": str(raw.get("title") or raw.get("$EVENT_TITLE") or ""),
        "alert_type": "reliability",
        "priority": _normalize_priority(raw.get("priority") or raw.get("$PRIORITY")),
        "tags": tags,
        "body": str(raw.get("body") or raw.get("$EVENT_MSG") or ""),
        "host": host,
        "timestamp": _normalize_timestamp(
            raw.get("timestamp") or raw.get("$DATE")
        ),
    }

    logger.info(
        "map_datadog_payload: alert_id=%s priority=%s host=%s tags=%d",
        alert["alert_id"],
        alert["priority"],
        alert["host"],
        len(tags),
    )
    return alert
