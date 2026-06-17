"""Incident registry lifecycle — v2 API (data-contracts §5)."""
from __future__ import annotations

from app import incidents


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alert(host: str = "auth-01") -> dict:
    return {
        "alert_id": "dd-test-01",
        "title": "Test alert",
        "alert_type": "reliability",
        "priority": "P2",
        "tags": [f"host:{host}"],
        "body": "Test body.",
        "host": host,
        "timestamp": "2026-06-15T09:14:00Z",
    }


# ---------------------------------------------------------------------------
# open_incident
# ---------------------------------------------------------------------------

def test_open_incident_starts_diagnosing():
    inc = incidents.open_incident(_alert())

    assert inc["status"] == "diagnosing"
    assert inc["decision"] is None
    assert inc["incident_id"].startswith("inc-")


def test_open_incident_sets_target_from_host():
    inc = incidents.open_incident(_alert("payment-gw"))

    assert inc["target"] == "payment-gw"


def test_open_incident_sets_execution_mode():
    inc = incidents.open_incident(_alert(), execution_mode="real")

    assert inc["execution_mode"] == "real"


def test_open_incident_default_execution_mode_is_simulate():
    inc = incidents.open_incident(_alert())

    assert inc["execution_mode"] == "simulate"


def test_get_incident_returns_same_object():
    inc = incidents.open_incident(_alert())

    assert incidents.get_incident(inc["incident_id"]) is inc


def test_get_unknown_incident_returns_none():
    assert incidents.get_incident("inc-nope") is None


def test_incident_ids_are_unique():
    ids = {incidents.open_incident(_alert())["incident_id"] for _ in range(50)}

    assert len(ids) == 50


# ---------------------------------------------------------------------------
# set_diagnosis
# ---------------------------------------------------------------------------

def test_set_diagnosis_attaches_and_returns_incident():
    inc = incidents.open_incident(_alert())
    diag = {"incident_type": "bad_deploy", "severity": "SEV-1", "affected_service": "payment-gw"}

    result = incidents.set_diagnosis(inc["incident_id"], diag)

    assert result is inc
    assert inc["diagnosis"]["incident_type"] == "bad_deploy"


def test_set_diagnosis_unknown_id_returns_none():
    assert incidents.set_diagnosis("inc-nope", {}) is None


# ---------------------------------------------------------------------------
# set_plan
# ---------------------------------------------------------------------------

def test_set_plan_populates_v1_compat_fields():
    inc = incidents.open_incident(_alert())
    plan = {
        "summary": "Rollback then restart.",
        "steps": [
            {"action": "rollback_deployment", "target": "payment-gw", "autonomy": "auto", "reversible": True, "description": "Rollback"},
            {"action": "restart_service", "target": "payment-gw", "autonomy": "auto", "reversible": True, "description": "Restart"},
        ],
        "script": "Do you approve the rollback?",
    }

    result = incidents.set_plan(inc["incident_id"], plan)

    assert result is inc
    assert inc["action"] == "rollback_deployment"
    assert inc["target"] == "payment-gw"
    assert inc["script"] == "Do you approve the rollback?"


def test_set_plan_unknown_id_returns_none():
    assert incidents.set_plan("inc-nope", {}) is None


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------

def test_set_status_transitions_correctly():
    inc = incidents.open_incident(_alert())

    incidents.set_status(inc["incident_id"], "remediating")

    assert inc["status"] == "remediating"


def test_set_status_unknown_id_returns_none():
    assert incidents.set_status("inc-nope", "resolved") is None


# ---------------------------------------------------------------------------
# add_attempt
# ---------------------------------------------------------------------------

def test_add_attempt_appends_to_list():
    inc = incidents.open_incident(_alert())
    attempt = {"action": "rollback_deployment", "target": "payment-gw", "actor": "auto", "result": "failed", "ts": "2026-06-15T09:14:05Z"}

    incidents.add_attempt(inc["incident_id"], attempt)

    assert len(inc["attempts"]) == 1
    assert inc["attempts"][0]["action"] == "rollback_deployment"


def test_add_attempt_unknown_id_returns_none():
    assert incidents.add_attempt("inc-nope", {}) is None


# ---------------------------------------------------------------------------
# assign_engineer
# ---------------------------------------------------------------------------

def test_assign_engineer_sets_field():
    inc = incidents.open_incident(_alert())
    engineer = {"id": "eng-01", "name": "Alex", "channels": ["slack"]}

    incidents.assign_engineer(inc["incident_id"], engineer)

    assert inc["assigned_engineer"]["id"] == "eng-01"


def test_assign_engineer_unknown_id_returns_none():
    assert incidents.assign_engineer("inc-nope", {}) is None


# ---------------------------------------------------------------------------
# set_decision + resolve_incident (v1 compat)
# ---------------------------------------------------------------------------

def test_set_decision_records_decision():
    inc = incidents.open_incident(_alert())

    incidents.set_decision(inc["incident_id"], "approve")

    assert inc["decision"] == "approve"


def test_resolve_incident_sets_resolved_and_decision():
    inc = incidents.open_incident(_alert())

    resolved = incidents.resolve_incident(inc["incident_id"], "deny")

    assert resolved["status"] == "resolved"
    assert resolved["decision"] == "deny"


def test_resolve_unknown_incident_returns_none():
    assert incidents.resolve_incident("inc-nope", "approve") is None
