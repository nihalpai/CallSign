"""Shared fixtures. The backend holds in-memory state at module scope, so every
test resets it to a clean slate to stay order-independent."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import state, incidents, events, deployments
from app.main import app

ALERT_PATH = Path(__file__).resolve().parent.parent / "data" / "mock_alerts" / "shellshock.json"


@pytest.fixture(autouse=True)
def reset_event_loop():
    """Ensure each test gets a fresh, open event loop (Python 3.9 compatibility).
    asyncio.run() closes the default loop; subsequent asyncio.Queue() calls fail."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    # Hermetic tests: never use the developer's real .env credentials or touch
    # external services (Lyzr, Slack, voice). Force the brain to the deterministic
    # fallback and all integrations to disabled, regardless of what's in .env.
    # Lyzr-path tests opt back in by setting these attrs themselves.
    from app import config, escalation
    from app.integrations import slack as slack_mod

    monkeypatch.delenv("LYZR_API_KEY", raising=False)
    # The brain reads these from config at call time:
    for attr in ("LYZR_API_KEY", "LYZR_DIAGNOSTICIAN_AGENT_ID",
                 "LYZR_STRATEGIST_AGENT_ID", "LYZR_VOICE_AGENT_ID"):
        monkeypatch.setattr(config, attr, None, raising=False)
    monkeypatch.setattr(config, "SLACK_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "VOICE_ENABLED", False, raising=False)
    # slack.py / escalation.py snapshot their toggles at import — patch those copies:
    monkeypatch.setattr(slack_mod, "SLACK_ENABLED", False, raising=False)
    monkeypatch.setattr(slack_mod, "SLACK_INTERACTIVE", False, raising=False)
    monkeypatch.setattr(escalation, "SLACK_ENABLED", False, raising=False)
    monkeypatch.setattr(escalation, "VOICE_ENABLED", False, raising=False)

    state._load()
    deployments._load()
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
