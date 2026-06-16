"""Incident registry lifecycle."""
from __future__ import annotations

from app import incidents


def test_open_incident_starts_awaiting_approval():
    inc = incidents.open_incident("isolate_container", "auth-01", "Approve?")

    assert inc["status"] == "awaiting_approval"
    assert inc["decision"] is None
    assert inc["incident_id"].startswith("inc-")
    assert inc["action"] == "isolate_container"
    assert inc["target"] == "auth-01"


def test_get_incident_returns_same_object():
    inc = incidents.open_incident("revoke_keys", "auth-01", "Approve?")

    assert incidents.get_incident(inc["incident_id"]) is inc


def test_get_unknown_incident_returns_none():
    assert incidents.get_incident("inc-nope") is None


def test_resolve_incident_records_decision():
    inc = incidents.open_incident("isolate_container", "auth-01", "Approve?")

    resolved = incidents.resolve_incident(inc["incident_id"], "approve")

    assert resolved["status"] == "resolved"
    assert resolved["decision"] == "approve"


def test_resolve_unknown_incident_returns_none():
    assert incidents.resolve_incident("inc-nope", "approve") is None


def test_incident_ids_are_unique():
    ids = {incidents.open_incident("isolate_container", "auth-01", "?")["incident_id"] for _ in range(50)}

    assert len(ids) == 50
