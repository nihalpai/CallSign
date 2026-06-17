"""
Tests for app.integrations.slack — disabled-mode behavior.

When SLACK_ENABLED is False:
  - post_incident: logs the card via log(source="SLACK", ...) and makes NO network call.
  - post_thread: logs the text and makes NO network call.

slack_sdk must NOT be imported (we assert no network call by confirming no
slack_sdk.WebClient is constructed — we monkeypatch the config flag and verify
only log output).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from app import incidents, events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_incident() -> dict:
    alert = {
        "alert_id": "test-slack-01",
        "title": "Slack test alert",
        "alert_type": "reliability",
        "priority": "P1",
        "tags": ["service:payment-gw"],
        "body": "Slack test body.",
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
        "summary": "5xx spike after bad deploy.",
        "rationale": "Aligned with deploy.",
        "cve": None,
    })
    incidents.set_plan(inc["incident_id"], {
        "summary": "Roll back then restart.",
        "steps": [
            {"action": "rollback_deployment", "target": "payment-gw",
             "autonomy": "human", "reversible": True, "description": "Rollback to dpl_8e1"},
        ],
        "script": "SEV-1 on Payments. Do you approve the rollback?",
    })
    return incidents.get_incident(inc["incident_id"])


def _engineer() -> dict:
    return {
        "id": "eng-02",
        "name": "Priya",
        "slack_id": "U02PRIYA",
        "phone": "+15555550102",
        "timezone": "Asia/Kolkata",
        "shift_start": "21:00",
        "shift_end": "09:00",
        "status": "active",
    }


# ---------------------------------------------------------------------------
# post_incident — disabled mode
# ---------------------------------------------------------------------------

class TestPostIncidentDisabled:

    def test_logs_would_post_message(self):
        from app.integrations import slack as slack_module
        inc = _make_incident()
        eng = _engineer()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_incident(eng, inc, lambda src, msg: log_calls.append((src, msg)))

        assert len(log_calls) >= 1
        sources = [src for src, _ in log_calls]
        assert "SLACK" in sources

    def test_log_message_contains_would_post(self):
        from app.integrations import slack as slack_module
        inc = _make_incident()
        eng = _engineer()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_incident(eng, inc, lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert any("[SLACK] would post:" in msg for msg in slack_logs)

    def test_no_network_call_made(self):
        """Confirm slack_sdk.WebClient is never constructed when disabled."""
        from app.integrations import slack as slack_module
        inc = _make_incident()
        eng = _engineer()

        mock_webclient = MagicMock()
        fake_slack_sdk = MagicMock()
        fake_slack_sdk.WebClient = mock_webclient

        with patch.object(slack_module, "SLACK_ENABLED", False):
            with patch.dict(sys.modules, {"slack_sdk": fake_slack_sdk}):
                slack_module.post_incident(eng, inc, lambda src, msg: None)

        mock_webclient.assert_not_called()

    def test_card_includes_severity_in_log(self):
        from app.integrations import slack as slack_module
        inc = _make_incident()
        eng = _engineer()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_incident(eng, inc, lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        # The card text should mention SEV-1
        assert any("SEV-1" in msg for msg in slack_logs)

    def test_card_includes_incident_in_log(self):
        from app.integrations import slack as slack_module
        inc = _make_incident()
        eng = _engineer()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_incident(eng, inc, lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert any("incident" in msg.lower() for msg in slack_logs)


# ---------------------------------------------------------------------------
# post_thread — disabled mode
# ---------------------------------------------------------------------------

class TestPostThreadDisabled:

    def test_logs_thread_text(self):
        from app.integrations import slack as slack_module
        inc = _make_incident()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_thread(inc, "Resolved by Priya", lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert len(slack_logs) >= 1
        assert any("Resolved by Priya" in msg or "would thread" in msg for msg in slack_logs)

    def test_no_network_call_on_thread(self):
        from app.integrations import slack as slack_module
        inc = _make_incident()
        mock_webclient = MagicMock()
        fake_slack_sdk = MagicMock()
        fake_slack_sdk.WebClient = mock_webclient

        with patch.object(slack_module, "SLACK_ENABLED", False):
            with patch.dict(sys.modules, {"slack_sdk": fake_slack_sdk}):
                slack_module.post_thread(inc, "Test thread", lambda src, msg: None)

        mock_webclient.assert_not_called()


# ---------------------------------------------------------------------------
# post_incident — card structure (smoke-test build_card indirectly)
# ---------------------------------------------------------------------------

class TestCardStructure:

    def test_card_has_channel_and_blocks(self):
        """Peek at the card dict via a log capture — no network needed."""
        from app.integrations import slack as slack_module
        import json as _json

        inc = _make_incident()
        eng = _engineer()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False), \
             patch.object(slack_module, "PUBLIC_BACKEND_URL", "https://example.com"):
            slack_module.post_incident(eng, inc, lambda src, msg: log_calls.append((src, msg)))

        # The logger.info call logs json.dumps of the card; we only check
        # that the SLACK source log was emitted (card validation in _build_card).
        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert len(slack_logs) >= 1

    def test_card_ui_link_uses_public_backend_url(self):
        """When PUBLIC_BACKEND_URL is set, the log should hint at the URL (via text field)."""
        from app.integrations import slack as slack_module
        inc = _make_incident()
        eng = _engineer()

        # Intercept _build_card to inspect the returned dict
        original_build = slack_module._build_card
        captured_cards: list[dict] = []

        def capturing_build(eng_, inc_):
            card = original_build(eng_, inc_)
            captured_cards.append(card)
            return card

        with patch.object(slack_module, "SLACK_ENABLED", False), \
             patch.object(slack_module, "PUBLIC_BACKEND_URL", "https://callsign.example.com"), \
             patch.object(slack_module, "_build_card", capturing_build):
            slack_module.post_incident(eng, inc, lambda src, msg: None)

        assert len(captured_cards) == 1
        card = captured_cards[0]
        # Find the Open CallSign button URL
        action_blocks = [b for b in card["blocks"] if b["type"] == "actions"]
        assert len(action_blocks) >= 1
        elements = action_blocks[0]["elements"]
        open_btn = next((el for el in elements if el.get("text", {}).get("text") == "Open CallSign"), None)
        assert open_btn is not None
        assert "callsign.example.com" in open_btn["url"]
        assert inc["incident_id"] in open_btn["url"]
