"""
Tests for app.integrations.slack — disabled-mode behavior for post_approval.

When SLACK_ENABLED is False:
  - post_approval: logs the card via log(source="SLACK", ...) and makes NO network call.
  - post_thread: logs the text and makes NO network call.

Also tests /slack/interactions resolving an apr-* request.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_req(**kwargs) -> dict:
    base = {
        "request_id": "apr-test01",
        "action": "restart_service",
        "target": "payment-gw",
        "context": "high error rate",
        "risk": "high",
        "reversible": True,
        "mode": "callback",
        "status": "awaiting_approval",
    }
    base.update(kwargs)
    return base


def _approver() -> dict:
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
# post_approval — disabled mode
# ---------------------------------------------------------------------------

class TestPostApprovalDisabled:

    def test_logs_would_post_message(self):
        from app.integrations import slack as slack_module
        req = _make_req()
        eng = _approver()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_approval(req, eng, lambda src, msg: log_calls.append((src, msg)))

        assert len(log_calls) >= 1
        sources = [src for src, _ in log_calls]
        assert "SLACK" in sources

    def test_log_message_contains_would_post(self):
        from app.integrations import slack as slack_module
        req = _make_req()
        eng = _approver()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_approval(req, eng, lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert any("[SLACK] would post:" in msg for msg in slack_logs)

    def test_no_network_call_made(self):
        from app.integrations import slack as slack_module
        req = _make_req()
        eng = _approver()

        mock_webclient = MagicMock()
        fake_slack_sdk = MagicMock()
        fake_slack_sdk.WebClient = mock_webclient

        with patch.object(slack_module, "SLACK_ENABLED", False):
            with patch.dict(sys.modules, {"slack_sdk": fake_slack_sdk}):
                slack_module.post_approval(req, eng, lambda src, msg: None)

        mock_webclient.assert_not_called()

    def test_card_contains_action(self):
        from app.integrations import slack as slack_module
        req = _make_req(action="delete_database")
        eng = _approver()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_approval(req, eng, lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert any("delete_database" in msg for msg in slack_logs)

    def test_card_contains_dangers_when_set(self):
        from app.integrations import slack as slack_module
        req = _make_req(dangers=["deletes all records", "irreversible"])
        eng = _approver()
        captured_cards: list[dict] = []
        original_build = slack_module._build_approval_card

        def capturing_build(r, a):
            card = original_build(r, a)
            captured_cards.append(card)
            return card

        with patch.object(slack_module, "SLACK_ENABLED", False), \
             patch.object(slack_module, "_build_approval_card", capturing_build):
            slack_module.post_approval(req, eng, lambda src, msg: None)

        assert len(captured_cards) == 1
        card_json = json.dumps(captured_cards[0])
        assert "deletes all records" in card_json
        assert "irreversible" in card_json

    def test_card_contains_estimated_tokens_when_set(self):
        from app.integrations import slack as slack_module
        req = _make_req(estimated_tokens=15000)
        eng = _approver()
        captured_cards: list[dict] = []
        original_build = slack_module._build_approval_card

        def capturing_build(r, a):
            card = original_build(r, a)
            captured_cards.append(card)
            return card

        with patch.object(slack_module, "SLACK_ENABLED", False), \
             patch.object(slack_module, "_build_approval_card", capturing_build):
            slack_module.post_approval(req, eng, lambda src, msg: None)

        card_json = json.dumps(captured_cards[0])
        assert "15,000" in card_json or "15000" in card_json

    def test_card_omits_dangers_section_when_none(self):
        from app.integrations import slack as slack_module
        req = _make_req(dangers=None)
        eng = _approver()
        captured_cards: list[dict] = []
        original_build = slack_module._build_approval_card

        def capturing_build(r, a):
            card = original_build(r, a)
            captured_cards.append(card)
            return card

        with patch.object(slack_module, "SLACK_ENABLED", False), \
             patch.object(slack_module, "_build_approval_card", capturing_build):
            slack_module.post_approval(req, eng, lambda src, msg: None)

        card_json = json.dumps(captured_cards[0])
        assert "Dangers" not in card_json

    def test_card_has_approve_deny_buttons_when_interactive(self):
        from app.integrations import slack as slack_module
        req = _make_req()
        eng = _approver()
        captured_cards: list[dict] = []
        original_build = slack_module._build_approval_card

        def capturing_build(r, a):
            card = original_build(r, a)
            captured_cards.append(card)
            return card

        with patch.object(slack_module, "SLACK_ENABLED", False), \
             patch.object(slack_module, "SLACK_INTERACTIVE", True), \
             patch.object(slack_module, "_build_approval_card", capturing_build):
            slack_module.post_approval(req, eng, lambda src, msg: None)

        card = captured_cards[0]
        action_blocks = [b for b in card["blocks"] if b["type"] == "actions"]
        assert len(action_blocks) >= 1
        elements = action_blocks[0]["elements"]
        action_ids = [el.get("action_id") for el in elements]
        assert "approve" in action_ids
        assert "deny" in action_ids

    def test_approve_button_value_is_request_id(self):
        from app.integrations import slack as slack_module
        req = _make_req(request_id="apr-abc123")
        eng = _approver()
        captured_cards: list[dict] = []
        original_build = slack_module._build_approval_card

        def capturing_build(r, a):
            card = original_build(r, a)
            captured_cards.append(card)
            return card

        with patch.object(slack_module, "SLACK_ENABLED", False), \
             patch.object(slack_module, "SLACK_INTERACTIVE", True), \
             patch.object(slack_module, "_build_approval_card", capturing_build):
            slack_module.post_approval(req, eng, lambda src, msg: None)

        card = captured_cards[0]
        action_blocks = [b for b in card["blocks"] if b["type"] == "actions"]
        elements = action_blocks[0]["elements"]
        approve_btn = next((el for el in elements if el.get("action_id") == "approve"), None)
        assert approve_btn is not None
        assert approve_btn["value"] == "apr-abc123"


# ---------------------------------------------------------------------------
# post_thread — disabled mode
# ---------------------------------------------------------------------------

class TestPostThreadDisabled:

    def test_logs_thread_text(self):
        from app.integrations import slack as slack_module
        req = _make_req()
        log_calls: list[tuple[str, str]] = []

        with patch.object(slack_module, "SLACK_ENABLED", False):
            slack_module.post_thread(req, "✅ Approved by eng-01", lambda src, msg: log_calls.append((src, msg)))

        slack_logs = [msg for src, msg in log_calls if src == "SLACK"]
        assert len(slack_logs) >= 1
        assert any("Approved by eng-01" in msg or "would thread" in msg for msg in slack_logs)

    def test_no_network_call_on_thread(self):
        from app.integrations import slack as slack_module
        req = _make_req()
        mock_webclient = MagicMock()
        fake_slack_sdk = MagicMock()
        fake_slack_sdk.WebClient = mock_webclient

        with patch.object(slack_module, "SLACK_ENABLED", False):
            with patch.dict(sys.modules, {"slack_sdk": fake_slack_sdk}):
                slack_module.post_thread(req, "Test thread", lambda src, msg: None)

        mock_webclient.assert_not_called()


# ---------------------------------------------------------------------------
# /slack/interactions — resolves an apr-* request
# ---------------------------------------------------------------------------

def _make_slack_signature(body: bytes, secret: str) -> tuple[str, str]:
    """Build a valid Slack signature for the given body."""
    ts = str(int(time.time()))
    base = f"v0:{ts}:{body.decode('utf-8')}"
    sig = "v0=" + hmac.new(
        secret.encode("utf-8"),
        base.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return ts, sig


class TestSlackInteractions:

    def _post_interaction(self, client, request_id: str, action_id: str, secret: str) -> any:
        payload = {
            "type": "block_actions",
            "user": {"id": "USLACK01", "username": "alice"},
            "actions": [{"action_id": action_id, "value": request_id}],
        }
        payload_json = json.dumps(payload)
        body = urllib.parse.urlencode({"payload": payload_json}).encode("utf-8")
        ts, sig = _make_slack_signature(body, secret)
        return client.post(
            "/slack/interactions",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )

    def test_interactions_disabled_returns_404(self, client, monkeypatch):
        from app import config
        from app.routes import slack as slack_route
        monkeypatch.setattr(config, "SLACK_INTERACTIVE", False)
        monkeypatch.setattr(slack_route, "SLACK_INTERACTIVE", False)

        resp = client.post("/slack/interactions", content=b"payload=%7B%7D",
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert resp.status_code == 404

    def test_approve_button_resolves_request(self, client, monkeypatch):
        from app import config
        from app.routes import slack as slack_route
        from app import requests as req_store

        secret = "test-signing-secret"
        monkeypatch.setattr(config, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(config, "SLACK_SIGNING_SECRET", secret)
        monkeypatch.setattr(slack_route, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(slack_route, "SLACK_SIGNING_SECRET", secret)

        # Create a pending request directly in the store
        req_store._requests["apr-slk01"] = {
            "request_id": "apr-slk01",
            "action": "restart_service",
            "target": "payment-gw",
            "status": "awaiting_approval",
            "mode": "callback",
            "outcome": None,
        }

        resp = self._post_interaction(client, "apr-slk01", "approve", secret)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        stored = req_store._requests["apr-slk01"]
        assert stored["status"] == "returned"
        assert stored["outcome"]["decision"] == "approve"
        assert stored["outcome"]["approved"] is True
        assert stored["outcome"]["actor"] == "USLACK01"

    def test_deny_button_resolves_request(self, client, monkeypatch):
        from app import config
        from app.routes import slack as slack_route
        from app import requests as req_store

        secret = "test-signing-secret-2"
        monkeypatch.setattr(config, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(config, "SLACK_SIGNING_SECRET", secret)
        monkeypatch.setattr(slack_route, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(slack_route, "SLACK_SIGNING_SECRET", secret)

        req_store._requests["apr-slk02"] = {
            "request_id": "apr-slk02",
            "action": "delete_table",
            "target": "db-01",
            "status": "awaiting_approval",
            "mode": "gate",
            "outcome": None,
        }

        resp = self._post_interaction(client, "apr-slk02", "deny", secret)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        stored = req_store._requests["apr-slk02"]
        assert stored["status"] == "denied"
        assert stored["outcome"]["decision"] == "deny"
        assert stored["outcome"]["approved"] is False

    def test_invalid_signature_returns_403(self, client, monkeypatch):
        from app import config
        from app.routes import slack as slack_route

        monkeypatch.setattr(config, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(config, "SLACK_SIGNING_SECRET", "correct-secret")
        monkeypatch.setattr(slack_route, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(slack_route, "SLACK_SIGNING_SECRET", "correct-secret")

        body = b"payload=%7B%7D"
        ts = str(int(time.time()))
        resp = client.post(
            "/slack/interactions",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=invalidsignature",
            },
        )
        assert resp.status_code == 403

    def test_unknown_request_id_returns_ok_with_warning(self, client, monkeypatch):
        from app import config
        from app.routes import slack as slack_route

        secret = "test-secret-3"
        monkeypatch.setattr(config, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(config, "SLACK_SIGNING_SECRET", secret)
        monkeypatch.setattr(slack_route, "SLACK_INTERACTIVE", True)
        monkeypatch.setattr(slack_route, "SLACK_SIGNING_SECRET", secret)

        resp = self._post_interaction(client, "apr-nonexistent", "approve", secret)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "warning" in body
