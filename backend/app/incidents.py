from __future__ import annotations
import random
import string
from datetime import datetime, timezone
from typing import Optional

# In-memory registry: incident_id -> incident dict
_incidents: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id() -> str:
    suffix = "".join(random.choices(string.hexdigits[:16], k=4))
    return f"inc-{suffix}"


def open_incident(action: str, target: str, script: str) -> dict:
    inc_id = _gen_id()
    inc = {
        "incident_id": inc_id,
        "status": "awaiting_approval",
        "decision": None,
        "action": action,
        "target": target,
        "script": script,
        "created_at": _now_iso(),
    }
    _incidents[inc_id] = inc
    return inc


def resolve_incident(incident_id: str, decision: str) -> Optional[dict]:
    inc = _incidents.get(incident_id)
    if inc is None:
        return None
    inc["status"] = "resolved"
    inc["decision"] = decision
    return inc


def get_incident(incident_id: str) -> Optional[dict]:
    return _incidents.get(incident_id)
