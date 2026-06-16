"""End-to-end HTTP loop: trigger -> incident -> execute, plus the SSE stream.
This is the Phase-3 'prove the loop' guarantee, exercised through FastAPI."""
from __future__ import annotations

import asyncio
import json

from app import state
from app.routes.stream import event_stream


def _status_of(server_id: str) -> str:
    return next(s["status"] for s in state.get_state()["servers"] if s["id"] == server_id)


def test_trigger_returns_incident_and_compromises_host(client, shellshock_alert):
    resp = client.post("/webhook/trigger", json=shellshock_alert)

    assert resp.status_code == 200
    assert resp.json()["incident_id"].startswith("inc-")
    assert _status_of("auth-01") == "compromised"


def test_trigger_then_get_incident(client, shellshock_alert):
    inc_id = client.post("/webhook/trigger", json=shellshock_alert).json()["incident_id"]

    resp = client.get(f"/incident/{inc_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "awaiting_approval"
    assert body["action"] == "isolate_container"
    assert body["target"] == "auth-01"


def test_approve_isolates_the_target(client, shellshock_alert):
    inc_id = client.post("/webhook/trigger", json=shellshock_alert).json()["incident_id"]

    resp = client.post("/execute", json={
        "incident_id": inc_id, "decision": "approve",
        "action": "isolate_container", "target": "auth-01",
    })

    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    assert resp.json()["decision"] == "approve"
    assert _status_of("auth-01") == "isolated"


def test_deny_leaves_host_compromised(client, shellshock_alert):
    inc_id = client.post("/webhook/trigger", json=shellshock_alert).json()["incident_id"]

    resp = client.post("/execute", json={
        "incident_id": inc_id, "decision": "deny",
        "action": "isolate_container", "target": "auth-01",
    })

    assert resp.json()["decision"] == "deny"
    assert _status_of("auth-01") == "compromised"


def test_execute_is_idempotent(client, shellshock_alert):
    inc_id = client.post("/webhook/trigger", json=shellshock_alert).json()["incident_id"]
    body = {"incident_id": inc_id, "decision": "approve",
            "action": "isolate_container", "target": "auth-01"}

    first = client.post("/execute", json=body)
    second = client.post("/execute", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "resolved"
    assert _status_of("auth-01") == "isolated"


def test_execute_unknown_incident_404(client):
    resp = client.post("/execute", json={
        "incident_id": "inc-nope", "decision": "approve",
        "action": "isolate_container", "target": "auth-01",
    })

    assert resp.status_code == 404


def test_get_unknown_incident_404(client):
    assert client.get("/incident/inc-nope").status_code == 404


def test_trigger_rejects_malformed_alert(client):
    # Missing required fields -> Pydantic 422.
    resp = client.post("/webhook/trigger", json={"title": "incomplete"})

    assert resp.status_code == 422


AWS_KEY_ALERT = {
    "alert_id": "dd-9", "title": "Leaked key", "alert_type": "security", "priority": "P2",
    "tags": ["service:auth", "host:auth-01"],
    "body": "Exposed AKIA credential detected in a public repository.",
    "host": "auth-01", "timestamp": "2026-06-15T00:00:00Z",
}


def test_trigger_survives_total_brain_failure(client, shellshock_alert, monkeypatch):
    # If run_brain itself raises, the trigger route's static fallback still opens
    # a usable incident — the demo loop must not die on a brain outage.
    def boom(alert, log):
        raise RuntimeError("brain dead")

    monkeypatch.setattr("app.brain.pipeline.run_brain", boom)

    resp = client.post("/webhook/trigger", json=shellshock_alert)

    assert resp.status_code == 200
    inc = client.get(f"/incident/{resp.json()['incident_id']}").json()
    assert inc["action"] == "isolate_container"
    assert inc["target"] == "auth-01"


def test_approve_non_isolate_action_leaves_status_unchanged(client):
    # revoke_keys is recognized but not implemented for the PoC: approving it
    # resolves the incident but does not flip the host to isolated.
    inc_id = client.post("/webhook/trigger", json=AWS_KEY_ALERT).json()["incident_id"]
    assert client.get(f"/incident/{inc_id}").json()["action"] == "revoke_keys"

    resp = client.post("/execute", json={
        "incident_id": inc_id, "decision": "approve",
        "action": "revoke_keys", "target": "auth-01",
    })

    assert resp.json()["status"] == "resolved"
    assert _status_of("auth-01") == "compromised"


def test_stream_first_event_is_state_snapshot():
    # The /stream endpoint is an infinite SSE generator, so we drive the real
    # generator directly, pull one event, and close it — with a hard timeout so
    # the test can never hang on the long-lived loop.
    async def first_event() -> dict:
        gen = event_stream()
        try:
            return await anext(gen)
        finally:
            await gen.aclose()

    evt = asyncio.run(asyncio.wait_for(first_event(), timeout=5))

    assert evt["event"] == "state"
    data = json.loads(evt["data"])
    assert any(s["id"] == "auth-01" for s in data["servers"])


def test_stream_forwards_published_events():
    # After the initial snapshot, the generator subscribes and forwards events.
    from app.events import emit_log

    async def second_event() -> dict:
        gen = event_stream()
        try:
            await anext(gen)  # consume initial state; generator now subscribes
            pending = asyncio.ensure_future(anext(gen))
            await asyncio.sleep(0.05)  # let the generator reach q.get()
            emit_log("AGENT", "cross-referencing runbook")
            return await pending
        finally:
            await gen.aclose()

    evt = asyncio.run(asyncio.wait_for(second_event(), timeout=5))

    assert evt["event"] == "log"
    assert json.loads(evt["data"])["message"] == "cross-referencing runbook"
