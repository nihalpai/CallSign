"""Tests for the generic approval-gate endpoints (POST /approvals, GET /approvals/{id}).

Covers:
  - blocking + async wait modes
  - callback mode execution
  - auth (key set vs unset)
  - timeout
  - decision wiring via /execute
  - estimated_tokens and dangers fields
"""
from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_CALLBACK_BODY = {
    "action": "Refund $1 to customer 42",
    "context": "duplicate charge test",
    "mode": "callback",
    "wait": "blocking",
    "timeout_sec": 5,
}

_MINIMAL_GATE_BODY = {
    "action": "restart_service",
    "target": "payment-gw",
    "context": "high error rate",
    "mode": "gate",
    "wait": "blocking",
    "timeout_sec": 5,
}


def _approve_request(client: TestClient, request_id: str, delay: float = 0.2) -> threading.Thread:
    def _do():
        time.sleep(delay)
        client.post("/execute", json={
            "request_id": request_id,
            "decision": "approve",
            "actor": "eng-01",
        })
    t = threading.Thread(target=_do, daemon=True)
    t.start()
    return t


def _deny_request(client: TestClient, request_id: str, delay: float = 0.2) -> threading.Thread:
    def _do():
        time.sleep(delay)
        client.post("/execute", json={
            "request_id": request_id,
            "decision": "deny",
            "actor": "eng-01",
        })
    t = threading.Thread(target=_do, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Blocking mode — approve
# ---------------------------------------------------------------------------

def test_blocking_approve_via_concurrent_execute(client):
    """Blocking POST /approvals returns approved DecisionOutcome when /execute fires in time."""
    result: dict = {}

    def blocking_call():
        resp = client.post("/approvals", json={
            **_MINIMAL_CALLBACK_BODY,
            "wait": "blocking",
            "timeout_sec": 4,
        })
        result["resp"] = resp

    call_thread = threading.Thread(target=blocking_call, daemon=True)
    call_thread.start()
    time.sleep(0.3)

    from app import requests as req_store
    pending = [r for r in req_store._requests.values() if r.get("status") == "awaiting_approval"]
    assert len(pending) >= 1, "Expected at least one awaiting request"
    req_id = pending[-1]["request_id"]

    client.post("/execute", json={
        "request_id": req_id,
        "decision": "approve",
        "actor": "eng-02",
    })

    call_thread.join(timeout=5)
    assert "resp" in result, "Blocking call did not return"

    resp = result["resp"]
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is True
    assert body["decision"] == "approve"
    assert body["actor"] == "eng-02"
    assert body["request_id"] == req_id


# ---------------------------------------------------------------------------
# Blocking mode — deny
# ---------------------------------------------------------------------------

def test_blocking_deny_returns_decision_outcome(client):
    """Blocking POST /approvals returns denied DecisionOutcome when /execute denies."""
    result: dict = {}

    def blocking_call():
        resp = client.post("/approvals", json={
            **_MINIMAL_CALLBACK_BODY,
            "wait": "blocking",
            "timeout_sec": 4,
        })
        result["resp"] = resp

    call_thread = threading.Thread(target=blocking_call, daemon=True)
    call_thread.start()
    time.sleep(0.3)

    from app import requests as req_store
    pending = [r for r in req_store._requests.values() if r.get("status") == "awaiting_approval"]
    req_id = pending[-1]["request_id"]

    client.post("/execute", json={
        "request_id": req_id,
        "decision": "deny",
        "actor": "eng-01",
    })

    call_thread.join(timeout=5)
    resp = result["resp"]
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is False
    assert body["decision"] == "deny"


# ---------------------------------------------------------------------------
# Async mode
# ---------------------------------------------------------------------------

def test_async_returns_request_id_immediately(client):
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body
    assert body["request_id"].startswith("apr-")
    assert body["status"] == "awaiting_approval"


def test_async_get_poll_shows_awaiting(client):
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    request_id = resp.json()["request_id"]

    poll = client.get(f"/approvals/{request_id}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "awaiting_approval"


def test_async_get_poll_shows_outcome_after_execute(client):
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    request_id = resp.json()["request_id"]

    client.post("/execute", json={
        "request_id": request_id,
        "decision": "approve",
        "actor": "eng-01",
    })

    poll = client.get(f"/approvals/{request_id}")
    assert poll.status_code == 200
    data = poll.json()
    assert data["status"] in ("returned", "approved", "executed")
    assert data["outcome"]["decision"] == "approve"
    assert data["outcome"]["approved"] is True


# ---------------------------------------------------------------------------
# estimated_tokens and dangers fields
# ---------------------------------------------------------------------------

def test_estimated_tokens_accepted_and_stored(client):
    """POST /approvals with estimated_tokens → stored and returned by GET."""
    resp = client.post("/approvals", json={
        **_MINIMAL_CALLBACK_BODY,
        "wait": "async",
        "estimated_tokens": 12345,
    })
    assert resp.status_code == 200
    req_id = resp.json()["request_id"]

    poll = client.get(f"/approvals/{req_id}")
    assert poll.status_code == 200
    assert poll.json()["estimated_tokens"] == 12345


def test_dangers_accepted_and_stored(client):
    """POST /approvals with dangers list → stored and returned by GET."""
    resp = client.post("/approvals", json={
        **_MINIMAL_CALLBACK_BODY,
        "wait": "async",
        "dangers": ["irreversible", "overwrites prod"],
    })
    assert resp.status_code == 200
    req_id = resp.json()["request_id"]

    poll = client.get(f"/approvals/{req_id}")
    assert poll.status_code == 200
    data = poll.json()
    assert data["dangers"] == ["irreversible", "overwrites prod"]


def test_estimated_tokens_none_when_not_provided(client):
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    req_id = resp.json()["request_id"]

    poll = client.get(f"/approvals/{req_id}")
    data = poll.json()
    assert data.get("estimated_tokens") is None


def test_dangers_none_when_not_provided(client):
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    req_id = resp.json()["request_id"]

    poll = client.get(f"/approvals/{req_id}")
    data = poll.json()
    assert data.get("dangers") is None


# ---------------------------------------------------------------------------
# Callback mode
# ---------------------------------------------------------------------------

def test_callback_mode_approve_returns_returned_status(client):
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    request_id = resp.json()["request_id"]

    client.post("/execute", json={
        "request_id": request_id,
        "decision": "approve",
        "actor": "eng-01",
    })

    poll = client.get(f"/approvals/{request_id}")
    assert poll.json()["status"] == "returned"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_auth_missing_key_rejected_when_key_set(client, monkeypatch):
    from app import config, auth as auth_mod
    monkeypatch.setattr(config, "APPROVAL_API_KEY", "secret-key")
    monkeypatch.setattr(auth_mod, "APPROVAL_API_KEY", "secret-key")

    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    assert resp.status_code == 401


def test_auth_wrong_key_rejected(client, monkeypatch):
    from app import config, auth as auth_mod
    monkeypatch.setattr(config, "APPROVAL_API_KEY", "secret-key")
    monkeypatch.setattr(auth_mod, "APPROVAL_API_KEY", "secret-key")

    resp = client.post(
        "/approvals",
        json={**_MINIMAL_CALLBACK_BODY, "wait": "async"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_auth_correct_key_passes(client, monkeypatch):
    from app import config, auth as auth_mod
    monkeypatch.setattr(config, "APPROVAL_API_KEY", "secret-key")
    monkeypatch.setattr(auth_mod, "APPROVAL_API_KEY", "secret-key")

    resp = client.post(
        "/approvals",
        json={**_MINIMAL_CALLBACK_BODY, "wait": "async"},
        headers={"X-API-Key": "secret-key"},
    )
    assert resp.status_code == 200


def test_auth_open_when_key_unset(client, monkeypatch):
    from app import config, auth as auth_mod
    monkeypatch.setattr(config, "APPROVAL_API_KEY", None)
    monkeypatch.setattr(auth_mod, "APPROVAL_API_KEY", None)

    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

def test_timeout_returns_timeout_decision(client):
    resp = client.post("/approvals", json={
        **_MINIMAL_CALLBACK_BODY,
        "wait": "blocking",
        "timeout_sec": 1,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "timeout"
    assert body["approved"] is False


# ---------------------------------------------------------------------------
# 404 on unknown request
# ---------------------------------------------------------------------------

def test_get_unknown_approval_404(client):
    resp = client.get("/approvals/apr-doesnotexist")
    assert resp.status_code == 404


def test_execute_unknown_approval_id_returns_404(client):
    resp = client.post("/execute", json={
        "request_id": "apr-does-not-exist",
        "decision": "approve",
        "actor": "eng-01",
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_execute_idempotent_on_already_decided(client):
    """Second /execute on an already-decided request is a no-op."""
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    request_id = resp.json()["request_id"]

    approve_body = {"request_id": request_id, "decision": "approve", "actor": "eng-01"}

    first = client.post("/execute", json=approve_body)
    second = client.post("/execute", json=approve_body)

    assert first.status_code == 200
    assert second.status_code == 200
    # Second call is a no-op — status unchanged
    assert second.json()["status"] in ("returned", "approved")


# ---------------------------------------------------------------------------
# incident_id alias compatibility
# ---------------------------------------------------------------------------

def test_execute_accepts_incident_id_alias(client):
    """The legacy incident_id field is accepted as an alias for request_id."""
    resp = client.post("/approvals", json={**_MINIMAL_CALLBACK_BODY, "wait": "async"})
    request_id = resp.json()["request_id"]

    exec_resp = client.post("/execute", json={
        "incident_id": request_id,
        "decision": "approve",
        "actor": "eng-01",
    })
    assert exec_resp.status_code == 200
    assert exec_resp.json()["outcome"]["approved"] is True
