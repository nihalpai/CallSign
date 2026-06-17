"""End-to-end HTTP loop tests for CallSign AI v2.

Proves the two required demo paths:
  1. Autonomy path  — bad_deploy (SEV-2): auto rollback fails, auto restart succeeds → resolved.
  2. Escalation path — shellshock (SEV-1): escalates → awaiting_approval → /execute approve → resolved.

Also covers: idempotent execute, deny, 404s, SSE stream, brain fallback.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app import state
from app.routes.stream import event_stream

_ALERTS_DIR = Path(__file__).resolve().parent.parent / "data" / "mock_alerts"


def _load_alert(name: str) -> dict:
    with open(_ALERTS_DIR / name) as f:
        return json.load(f)


def _status_of(server_id: str) -> str:
    return next(s["status"] for s in state.get_state()["servers"] if s["id"] == server_id)


# ---------------------------------------------------------------------------
# Demo path 1 — Autonomy (bad_deploy, SEV-2)
# ---------------------------------------------------------------------------

def test_autonomy_path_bad_deploy(client):
    """Trigger bad_deploy → rollback fails verify → restart succeeds verify → resolved."""
    alert = _load_alert("bad_deploy.json")
    resp = client.post("/webhook/trigger", json=alert)

    assert resp.status_code == 200
    inc_id = resp.json()["incident_id"]
    assert inc_id.startswith("inc-")

    inc = client.get(f"/incident/{inc_id}").json()

    # Auto-remediation ran to completion
    assert inc["status"] == "resolved", f"Expected resolved, got {inc['status']}"

    # Two auto steps were attempted
    attempts = inc["attempts"]
    assert len(attempts) >= 2, f"Expected at least 2 attempts, got {attempts}"
    actions = [a["action"] for a in attempts]
    assert "rollback_deployment" in actions
    assert "restart_service" in actions

    # All auto attempts are actor=auto
    for attempt in attempts:
        assert attempt["actor"] == "auto"

    # Final server status: recovered (restart_service sets this)
    assert _status_of("payment-gw") == "recovered"


def test_autonomy_path_no_human_escalation(client):
    """Bad deploy at SEV-2 must not escalate to a human engineer."""
    alert = _load_alert("bad_deploy.json")
    resp = client.post("/webhook/trigger", json=alert)
    inc = client.get(f"/incident/{resp.json()['incident_id']}").json()

    assert inc["assigned_engineer"] is None
    assert inc["status"] == "resolved"


# ---------------------------------------------------------------------------
# Demo path 2 — Escalation (shellshock, SEV-1)
# ---------------------------------------------------------------------------

def test_escalation_path_shellshock_awaits_approval(client):
    """Shellshock (SEV-1) exceeds gate → escalates → awaiting_approval, engineer assigned."""
    alert = _load_alert("shellshock.json")
    resp = client.post("/webhook/trigger", json=alert)
    assert resp.status_code == 200

    inc_id = resp.json()["incident_id"]
    inc = client.get(f"/incident/{inc_id}").json()

    assert inc["status"] == "awaiting_approval", f"Expected awaiting_approval, got {inc['status']}"
    assert inc["assigned_engineer"] is not None
    assert inc["assigned_engineer"]["id"] in ("eng-01", "eng-02")


def test_escalation_path_approve_resolves(client):
    """After escalation, /execute approve → auth-01 isolated, incident resolved."""
    alert = _load_alert("shellshock.json")
    inc_id = client.post("/webhook/trigger", json=alert).json()["incident_id"]

    resp = client.post("/execute", json={
        "incident_id": inc_id,
        "decision": "approve",
        "action": "isolate_container",
        "target": "auth-01",
        "actor": "eng-01",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["decision"] == "approve"
    assert _status_of("auth-01") == "isolated"


def test_escalation_path_approve_idempotent(client):
    """Second /execute on an already-resolved incident is a no-op (returns resolved)."""
    alert = _load_alert("shellshock.json")
    inc_id = client.post("/webhook/trigger", json=alert).json()["incident_id"]

    approve_body = {
        "incident_id": inc_id,
        "decision": "approve",
        "action": "isolate_container",
        "target": "auth-01",
        "actor": "eng-01",
    }

    first = client.post("/execute", json=approve_body)
    second = client.post("/execute", json=approve_body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "resolved"
    # Server still isolated — second call did not double-execute
    assert _status_of("auth-01") == "isolated"


# ---------------------------------------------------------------------------
# Deny flow
# ---------------------------------------------------------------------------

def test_deny_sets_failed_and_does_not_change_server_status(client):
    """Deny on escalated incident → status=failed, server stays compromised."""
    alert = _load_alert("shellshock.json")
    inc_id = client.post("/webhook/trigger", json=alert).json()["incident_id"]

    resp = client.post("/execute", json={
        "incident_id": inc_id,
        "decision": "deny",
        "action": "isolate_container",
        "target": "auth-01",
        "actor": "eng-01",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["decision"] == "deny"
    # Host was set to compromised by trigger (security incident_type)
    assert _status_of("auth-01") == "compromised"


def test_deny_idempotent(client):
    """Second /execute after deny is a no-op (incident in terminal state)."""
    alert = _load_alert("shellshock.json")
    inc_id = client.post("/webhook/trigger", json=alert).json()["incident_id"]
    deny_body = {"incident_id": inc_id, "decision": "deny", "action": "isolate_container", "target": "auth-01", "actor": "eng-01"}

    first = client.post("/execute", json=deny_body)
    second = client.post("/execute", json=deny_body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# 404s
# ---------------------------------------------------------------------------

def test_execute_unknown_incident_404(client):
    resp = client.post("/execute", json={
        "incident_id": "inc-nope",
        "decision": "approve",
        "action": "isolate_container",
        "target": "auth-01",
        "actor": "auto",
    })
    assert resp.status_code == 404


def test_get_unknown_incident_404(client):
    assert client.get("/incident/inc-nope").status_code == 404


# ---------------------------------------------------------------------------
# Trigger basics
# ---------------------------------------------------------------------------

def test_trigger_returns_incident_id(client):
    alert = _load_alert("shellshock.json")
    resp = client.post("/webhook/trigger", json=alert)
    assert resp.status_code == 200
    assert resp.json()["incident_id"].startswith("inc-")


def test_trigger_sets_server_compromised_for_security(client):
    """Shellshock (security incident_type) → server status = compromised."""
    alert = _load_alert("shellshock.json")
    client.post("/webhook/trigger", json=alert)
    assert _status_of("auth-01") == "compromised"


def test_trigger_accepts_raw_datadog_payload(client):
    """A raw Datadog-shaped payload is accepted and produces an incident."""
    raw = {
        "alert_id": "dd-raw-001",
        "title": "Elevated 5xx rate",
        "priority": "P2",
        "tags": "service:web-01,host:web-01",
        "body": "Error rate elevated",
        "host": "web-01",
        "timestamp": "1718444040000",
    }
    resp = client.post("/webhook/trigger", json=raw)
    assert resp.status_code == 200
    assert resp.json()["incident_id"].startswith("inc-")


def test_trigger_get_incident_has_diagnosis_and_plan(client):
    """Triggered incident should have non-null diagnosis and plan."""
    alert = _load_alert("shellshock.json")
    inc_id = client.post("/webhook/trigger", json=alert).json()["incident_id"]
    inc = client.get(f"/incident/{inc_id}").json()
    assert inc["diagnosis"] is not None
    assert inc["plan"] is not None
    assert len(inc["plan"]["steps"]) > 0


# ---------------------------------------------------------------------------
# Brain fallback survival
# ---------------------------------------------------------------------------

def test_trigger_survives_total_brain_failure(client, monkeypatch):
    """If run_brain raises, static fallback still opens a usable incident."""
    def boom(alert, log):
        raise RuntimeError("brain dead")

    monkeypatch.setattr("app.brain.pipeline.run_brain", boom)

    alert = _load_alert("shellshock.json")
    resp = client.post("/webhook/trigger", json=alert)

    assert resp.status_code == 200
    inc = client.get(f"/incident/{resp.json()['incident_id']}").json()
    # Fallback plan's first step for shellshock = isolate_container (human autonomy → escalated)
    assert inc["action"] in ("isolate_container", "revoke_keys", "restart_service", "rollback_deployment")


# ---------------------------------------------------------------------------
# Incident endpoint
# ---------------------------------------------------------------------------

def test_get_incident_returns_full_object(client):
    alert = _load_alert("shellshock.json")
    inc_id = client.post("/webhook/trigger", json=alert).json()["incident_id"]
    inc = client.get(f"/incident/{inc_id}").json()

    assert inc["incident_id"] == inc_id
    assert "status" in inc
    assert "execution_mode" in inc
    assert "created_at" in inc


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

def test_stream_first_event_is_state_snapshot():
    """The first SSE event from /stream must be the current infra state."""
    async def first_event() -> dict:
        gen = event_stream()
        try:
            return await gen.__anext__()
        finally:
            await gen.aclose()

    evt = asyncio.run(asyncio.wait_for(first_event(), timeout=5))

    assert evt["event"] == "state"
    data = json.loads(evt["data"])
    assert any(s["id"] == "auth-01" for s in data["servers"])


def test_stream_forwards_published_events():
    """After the initial snapshot, published SSE events are forwarded to subscribers."""
    from app.events import emit_log

    async def second_event() -> dict:
        gen = event_stream()
        try:
            await gen.__anext__()  # consume initial state; generator now subscribes
            pending = asyncio.ensure_future(gen.__anext__())
            await asyncio.sleep(0.05)  # let the generator reach q.get()
            emit_log("AGENT", "cross-referencing runbook")
            return await pending
        finally:
            await gen.aclose()

    evt = asyncio.run(asyncio.wait_for(second_event(), timeout=5))

    assert evt["event"] == "log"
    assert json.loads(evt["data"])["message"] == "cross-referencing runbook"
