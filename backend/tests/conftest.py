"""Shared fixtures. The backend holds in-memory state at module scope, so every
test resets it to a clean slate to stay order-independent."""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import state, incidents, events
from app.main import app

ALERT_PATH = Path(__file__).resolve().parent.parent / "data" / "mock_alerts" / "shellshock.json"


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    # Ensure the brain uses the deterministic fallback (no network) in tests.
    monkeypatch.delenv("LYZR_API_KEY", raising=False)
    state._load()
    incidents._incidents.clear()
    events._subscribers.clear()
    yield
    incidents._incidents.clear()
    events._subscribers.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def shellshock_alert() -> dict:
    with open(ALERT_PATH) as f:
        return json.load(f)
