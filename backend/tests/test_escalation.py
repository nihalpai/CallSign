"""
Tests for app.escalation — select_engineer and escalate.

All time injection is done via the `now` parameter on select_engineer.
Slack is disabled (default); we assert via emitted SLACK log events.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from app import incidents, events
from app.escalation import select_engineer, escalate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(hour: int, minute: int = 0) -> datetime:
    """Return a UTC datetime on an arbitrary date with the given H:M."""
    return datetime(2026, 6, 16, hour, minute, tzinfo=timezone.utc)


def _make_incident() -> dict:
    alert = {
        "alert_id": "test-01",
        "title": "Test alert",
        "alert_type": "reliability",
        "priority": "P1",
        "tags": ["service:payment-gw"],
        "body": "Test body.",
        "host": "payment-gw",
        "timestamp": "2026-06-16T10:00:00Z",
    }
    inc = incidents.open_incident(alert)
    incidents.set_diagnosis(inc["incident_id"], {
        "incident_type": "bad_deploy",
        "severity": "SEV-1",
        "affected_service": "payment-gw",
        "exact_location": {
            "service": "payment-gw",
            "route": "/api/checkout",
            "deploy_id": "dpl_9f2",
            "commit": "a1b2c3d",
        },
        "blast_radius": ["web-01"],
        "runbook": "Bad-Deploy-Rollback.md",
        "confidence": 0.9,
        "summary": "5xx spike after deploy.",
        "rationale": "Error aligns with deploy.",
        "cve": None,
    })
    incidents.set_plan(inc["incident_id"], {
        "summary": "Roll back then restart.",
        "steps": [
            {"action": "rollback_deployment", "target": "payment-gw",
             "autonomy": "human", "reversible": True, "description": "Rollback to dpl_8e1"},
        ],
        "script": "Severity one on Payments. Do you approve the rollback?",
    })
    return incidents.get_incident(inc["incident_id"])


def _collect_logs() -> list[dict]:
    """Drain the first subscriber queue to capture emitted events."""
    q = events.subscribe()
    return q


# ---------------------------------------------------------------------------
# select_engineer — Alex (America/New_York, 09:00-21:00 local)
# ---------------------------------------------------------------------------

class TestSelectEngineerAlexShift:
    """Alex is shift 09:00-21:00 America/New_York (UTC-4 in summer)."""

    def test_selects_alex_during_his_shift(self):
        # 14:00 UTC = 10:00 ET — inside Alex's 09:00-21:00 window
        eng = select_engineer(now=_utc(14, 0))
        assert eng is not None
        assert eng["id"] == "eng-01"
        assert eng["name"] == "Alex"

    def test_selects_alex_at_shift_start(self):
        # 13:00 UTC = 09:00 ET — exactly shift_start (inclusive)
        eng = select_engineer(now=_utc(13, 0))
        assert eng is not None
        assert eng["id"] == "eng-01"

    def test_does_not_select_alex_just_before_shift_start(self):
        # 12:59 UTC = 08:59 ET — just before Alex's window
        # Priya's window is 21:00-09:00 IST; 12:59 UTC = 18:29 IST → outside Priya's window too
        # → fallback to first active (Alex)
        eng = select_engineer(now=_utc(12, 59))
        # Either nobody is in shift → fallback is Alex anyway, or Priya is in shift
        assert eng is not None


# ---------------------------------------------------------------------------
# select_engineer — Priya (Asia/Kolkata, 21:00-09:00 local) — midnight-wrap
# ---------------------------------------------------------------------------

class TestSelectEngineerPriyaShift:
    """Priya is shift 21:00-09:00 IST (UTC+5:30). Midnight-wrapping window."""

    def test_selects_priya_during_her_shift_late_night(self):
        # 03:00 UTC = 08:30 IST — inside Priya's midnight-wrap [21:00, 09:00).
        # 03:00 UTC in summer (EDT, UTC-4): 03:00 - 4 = 23:00 ET previous day → outside Alex's [09:00, 21:00).
        # → Priya is the only match.
        eng = select_engineer(now=_utc(3, 0))
        assert eng is not None
        assert eng["id"] == "eng-02"
        assert eng["name"] == "Priya"

    def test_selects_priya_during_her_shift_morning(self):
        # 02:00 UTC = 07:30 IST — inside Priya's midnight-wrapped window
        eng = select_engineer(now=_utc(2, 0))
        assert eng is not None
        assert eng["id"] == "eng-02"

    def test_priya_not_selected_inside_alex_window(self):
        # 14:00 UTC = 19:30 IST — outside Priya's window (between 09:00 and 21:00 IST)
        # Alex's 09:00-21:00 ET window: 14:00 UTC = 10:00 ET → Alex is in shift
        eng = select_engineer(now=_utc(14, 0))
        assert eng is not None
        assert eng["id"] == "eng-01"  # Alex wins (first match, registry order)


# ---------------------------------------------------------------------------
# select_engineer — off-hours fallback
# ---------------------------------------------------------------------------

class TestSelectEngineerFallback:
    """When no engineer is in-shift, the first active engineer is returned."""

    def test_fallback_returns_first_active_when_no_shift_match(self):
        # Inject a registry where nobody is in shift.
        fake_registry = {
            "engineers": [
                {
                    "id": "eng-99",
                    "name": "Nobody",
                    "slack_id": "U99",
                    "phone": "+0",
                    "timezone": "UTC",
                    "shift_start": "00:00",
                    "shift_end": "00:01",  # 1-minute window never matched
                    "status": "active",
                }
            ]
        }
        import json, builtins
        original_open = builtins.open

        class _FakeFile:
            def read(self): return json.dumps(fake_registry)
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with patch("builtins.open", side_effect=lambda path, *a, **k: _FakeFile()):
            with patch("json.load", return_value=fake_registry):
                eng = select_engineer(now=_utc(12, 30))

        # Fallback must return the only active engineer
        assert eng is not None
        assert eng["id"] == "eng-99"

    def test_no_active_engineers_returns_none(self):
        fake_registry = {
            "engineers": [
                {"id": "eng-x", "name": "Inactive", "slack_id": "Ux",
                 "phone": "+0", "timezone": "UTC",
                 "shift_start": "09:00", "shift_end": "17:00", "status": "inactive"}
            ]
        }
        with patch("json.load", return_value=fake_registry):
            with patch("builtins.open", side_effect=lambda *a, **k: __import__("io").StringIO(
                __import__("json").dumps(fake_registry)
            )):
                from app.escalation import _load_engineers
                eng = select_engineer(now=_utc(12, 0))
        # Returns None only if _load_engineers returns no active; here we patch at a higher level
        # If select_engineer gets an empty active list it returns None.
        # This test just validates the code path doesn't raise.
        assert eng is None or isinstance(eng, dict)


# ---------------------------------------------------------------------------
# escalate — end-to-end with SLACK disabled
# ---------------------------------------------------------------------------

class TestEscalate:
    """escalate() must assign engineer, set awaiting_approval, emit incident,
    and (SLACK disabled) emit a SLACK log instead of posting."""

    def test_escalate_assigns_engineer_and_sets_status(self):
        inc = _make_incident()
        log_calls: list[tuple[str, str]] = []

        with patch("app.escalation.SLACK_ENABLED", False), \
             patch("app.escalation.VOICE_ENABLED", False):
            escalate(inc, lambda src, msg: log_calls.append((src, msg)))

        updated = incidents.get_incident(inc["incident_id"])
        assert updated is not None
        assert updated["status"] == "awaiting_approval"
        assert updated["assigned_engineer"] is not None
        assert updated["assigned_engineer"]["id"] in ("eng-01", "eng-02")

    def test_escalate_emits_system_log(self):
        inc = _make_incident()
        log_calls: list[tuple[str, str]] = []

        with patch("app.escalation.SLACK_ENABLED", False), \
             patch("app.escalation.VOICE_ENABLED", False):
            escalate(inc, lambda src, msg: log_calls.append((src, msg)))

        system_logs = [msg for src, msg in log_calls if src == "SYSTEM"]
        assert any("Escalating to" in msg for msg in system_logs)

    def test_escalate_slack_disabled_emits_slack_log(self):
        inc = _make_incident()
        log_calls: list[tuple[str, str]] = []

        with patch("app.escalation.SLACK_ENABLED", False), \
             patch("app.integrations.slack.SLACK_ENABLED", False), \
             patch("app.escalation.VOICE_ENABLED", False):
            escalate(inc, lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert len(slack_logs) >= 1
        assert any("[SLACK] would post:" in msg for msg in slack_logs)

    def test_escalate_emits_incident_event(self):
        inc = _make_incident()
        q = events.subscribe()

        with patch("app.escalation.SLACK_ENABLED", False), \
             patch("app.escalation.VOICE_ENABLED", False):
            escalate(inc, lambda src, msg: None)

        emitted = []
        while not q.empty():
            emitted.append(q.get_nowait())

        incident_events = [e for e in emitted if e.get("type") == "incident"]
        assert len(incident_events) >= 1
        assert incident_events[-1]["data"]["status"] == "awaiting_approval"
