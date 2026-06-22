"""
Tests for enrichment + smart triage:
  - app.escalation.select_approver — expertise routing, fallback
  - app.enrichment.enrich_request — risk inference from dangers/tokens/context,
                                     summary building, never decides
  - End-to-end: POST /approvals with dangers + estimated_tokens → GET shows them
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.enrichment import enrich_request
from app.main import app


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 16, hour, minute, tzinfo=timezone.utc)


_NOOP_LOG = lambda src, msg: None


# ─────────────────────────────────────────────────────────────────────────────
# 1. select_approver — expertise routing
# ─────────────────────────────────────────────────────────────────────────────

class TestSelectApprover:
    # 14:00 UTC = 10:00 ET → Alex in shift; 03:00 UTC = 08:30 IST → Priya in shift
    _ALEX_HOUR = _utc(14, 0)
    _PRIYA_HOUR = _utc(3, 0)

    def test_expertise_routing_returns_owner_for_known_area(self):
        from app import config
        from app.escalation import select_approver

        with patch.object(config, "EXPERTISE_ROUTING", True):
            with patch("app.escalation.EXPERTISE_ROUTING", True):
                eng = select_approver(area="payment-gw", now=self._PRIYA_HOUR)

        assert eng is not None
        assert eng["id"] == "eng-02"
        assert eng["name"] == "Priya"

    def test_expertise_routing_returns_alex_for_auth_area(self):
        from app import config
        from app.escalation import select_approver

        with patch.object(config, "EXPERTISE_ROUTING", True):
            with patch("app.escalation.EXPERTISE_ROUTING", True):
                eng = select_approver(area="auth-01", now=self._ALEX_HOUR)

        assert eng is not None
        assert eng["id"] == "eng-01"

    def test_expertise_routing_falls_back_to_oncall_when_owner_unavailable(self):
        from app import config
        from app.escalation import select_approver

        with patch.object(config, "EXPERTISE_ROUTING", True):
            with patch("app.escalation.EXPERTISE_ROUTING", True):
                eng = select_approver(area="payment-gw", now=self._ALEX_HOUR)

        assert eng is not None
        assert eng["id"] in ("eng-01", "eng-02")

    def test_expertise_routing_falls_back_when_no_owner(self):
        from app import config
        from app.escalation import select_approver

        with patch.object(config, "EXPERTISE_ROUTING", True):
            with patch("app.escalation.EXPERTISE_ROUTING", True):
                eng = select_approver(area="nonexistent-service-xyz", now=self._ALEX_HOUR)

        assert eng is not None
        assert eng["id"] == "eng-01"

    def test_expertise_routing_off_uses_oncall(self):
        from app.escalation import select_approver

        with patch("app.escalation.EXPERTISE_ROUTING", False):
            eng = select_approver(area="payment-gw", now=self._ALEX_HOUR)

        assert eng is not None
        assert eng["id"] == "eng-01"

    def test_select_approver_no_area_uses_oncall(self):
        from app import config
        from app.escalation import select_approver

        with patch.object(config, "EXPERTISE_ROUTING", True):
            with patch("app.escalation.EXPERTISE_ROUTING", True):
                eng = select_approver(area=None, now=self._ALEX_HOUR)

        assert eng is not None


# ─────────────────────────────────────────────────────────────────────────────
# 2. enrich_request — risk inference
# ─────────────────────────────────────────────────────────────────────────────

class TestEnrichRequest:

    def _make_req(self, **kwargs) -> dict:
        base = {
            "request_id": "apr-test",
            "action": "restart_service",
            "target": "payment-gw",
            "context": "high error rate",
            "diagnostics": None,
            "risk": None,
            "dangers": None,
            "estimated_tokens": None,
            "reversible": True,
            "mode": "gate",
            "status": "created",
        }
        base.update(kwargs)
        return base

    def test_sets_risk_when_absent(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req()
            result = enrich_request(req, _NOOP_LOG)
        assert result.get("risk") in ("low", "medium", "high")

    def test_does_not_override_caller_risk(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(risk="low")
            result = enrich_request(req, _NOOP_LOG)
        assert result["risk"] == "low"

    def test_sets_enrichment_summary(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req()
            result = enrich_request(req, _NOOP_LOG)
        assert "enrichment_summary" in result
        assert len(result["enrichment_summary"]) > 0

    def test_high_risk_from_irreversible_danger(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(dangers=["irreversible operation on prod database"])
            result = enrich_request(req, _NOOP_LOG)
        assert result["risk"] == "high"

    def test_high_risk_from_delete_danger(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(dangers=["will delete all records"])
            result = enrich_request(req, _NOOP_LOG)
        assert result["risk"] == "high"

    def test_high_risk_from_large_token_count(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(estimated_tokens=50000)
            result = enrich_request(req, _NOOP_LOG)
        assert result["risk"] == "high"

    def test_low_risk_when_no_signals(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(context="minor config tweak", estimated_tokens=100)
            result = enrich_request(req, _NOOP_LOG)
        assert result["risk"] in ("low", "medium")

    def test_summary_includes_dangers(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(dangers=["drops prod table"])
            result = enrich_request(req, _NOOP_LOG)
        assert "drops prod table" in result["enrichment_summary"]

    def test_summary_includes_estimated_tokens(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(estimated_tokens=5000)
            result = enrich_request(req, _NOOP_LOG)
        assert "5000" in result["enrichment_summary"] or "estimated tokens" in result["enrichment_summary"].lower()

    def test_never_sets_decision_or_approved(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req()
            result = enrich_request(req, _NOOP_LOG)
        assert "decision" not in result or result.get("decision") is None
        assert "approved" not in result or result.get("approved") is None

    def test_does_not_raise_on_malformed_context(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            req = self._make_req(context=None, dangers=None, estimated_tokens=None)
            result = enrich_request(req, _NOOP_LOG)
        assert result is not None

    def test_no_op_when_enrich_disabled(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", False):
            req = self._make_req()
            result = enrich_request(req, _NOOP_LOG)
        assert result is not None

    def test_robust_against_exception_in_do_enrich(self):
        from app import config
        with patch.object(config, "ENRICH_REQUESTS", True):
            with patch("app.enrichment._do_enrich", side_effect=RuntimeError("boom")):
                req = self._make_req()
                result = enrich_request(req, _NOOP_LOG)
        assert result["request_id"] == "apr-test"


# ─────────────────────────────────────────────────────────────────────────────
# 3. End-to-end: POST /approvals with dangers + estimated_tokens
# ─────────────────────────────────────────────────────────────────────────────

class TestE2EWithDangersAndTokens:

    _BODY = {
        "action": "drop_table",
        "target": "db-01",
        "context": "cleanup old records",
        "mode": "callback",
        "wait": "async",
        "dangers": ["irreversible", "deletes all rows"],
        "estimated_tokens": 20000,
    }

    def test_stored_request_has_dangers(self, monkeypatch):
        from app import config
        monkeypatch.setattr(config, "ENRICH_REQUESTS", True)
        with TestClient(app) as client:
            post_resp = client.post("/approvals", json=self._BODY)
            assert post_resp.status_code == 200
            req_id = post_resp.json()["request_id"]

            get_resp = client.get(f"/approvals/{req_id}")
            assert get_resp.status_code == 200
            data = get_resp.json()

        assert data.get("dangers") == ["irreversible", "deletes all rows"]

    def test_stored_request_has_estimated_tokens(self, monkeypatch):
        from app import config
        monkeypatch.setattr(config, "ENRICH_REQUESTS", True)
        with TestClient(app) as client:
            post_resp = client.post("/approvals", json=self._BODY)
            req_id = post_resp.json()["request_id"]

            get_resp = client.get(f"/approvals/{req_id}")
            data = get_resp.json()

        assert data.get("estimated_tokens") == 20000

    def test_risk_is_high_due_to_dangers(self, monkeypatch):
        from app import config
        monkeypatch.setattr(config, "ENRICH_REQUESTS", True)
        with TestClient(app) as client:
            post_resp = client.post("/approvals", json=self._BODY)
            req_id = post_resp.json()["request_id"]

            get_resp = client.get(f"/approvals/{req_id}")
            data = get_resp.json()

        assert data.get("risk") == "high"

    def test_enrichment_summary_present(self, monkeypatch):
        from app import config
        monkeypatch.setattr(config, "ENRICH_REQUESTS", True)
        with TestClient(app) as client:
            post_resp = client.post("/approvals", json=self._BODY)
            req_id = post_resp.json()["request_id"]
            get_resp = client.get(f"/approvals/{req_id}")
            data = get_resp.json()

        assert data.get("enrichment_summary") is not None
        assert len(data["enrichment_summary"]) > 0

    def test_request_without_dangers_or_tokens_still_creates_ok(self, monkeypatch):
        from app import config
        monkeypatch.setattr(config, "ENRICH_REQUESTS", True)
        body = {
            "action": "restart_service",
            "target": "web-01",
            "context": "manual restart needed",
            "mode": "callback",
            "wait": "async",
        }
        with TestClient(app) as client:
            post_resp = client.post("/approvals", json=body)
        assert post_resp.status_code == 200
        assert "request_id" in post_resp.json()

    def test_post_approval_disabled_logs_card_with_dangers_and_tokens(self, monkeypatch):
        """post_approval (disabled mode) logs a card containing dangers + token count."""
        from app.integrations import slack as slack_module
        req = {
            "request_id": "apr-logtest",
            "action": "drop_table",
            "target": "db-01",
            "context": "cleanup",
            "risk": "high",
            "dangers": ["irreversible", "deletes all rows"],
            "estimated_tokens": 20000,
            "status": "awaiting_approval",
        }
        eng = {
            "id": "eng-01",
            "name": "Alex",
            "slack_id": "U01ALEX",
        }
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
        # dangers present
        assert "irreversible" in card_json
        assert "deletes all rows" in card_json
        # token count present
        assert "20,000" in card_json or "20000" in card_json


import json  # noqa: E402 — needed for test_post_approval_disabled_logs_card_with_dangers_and_tokens
