"""Shared fixtures. The backend holds in-memory state at module scope, so every
test resets it to a clean slate to stay order-independent."""
from __future__ import annotations
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import events, requests as apr_requests
from app.main import app


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
    # external services (Slack). Force all integrations to disabled.
    from app import config
    from app.integrations import slack as slack_mod

    monkeypatch.setattr(config, "SLACK_ENABLED", False, raising=False)
    monkeypatch.setattr(slack_mod, "SLACK_ENABLED", False, raising=False)
    monkeypatch.setattr(slack_mod, "SLACK_INTERACTIVE", False, raising=False)

    # Reset auth warning flag so tests that toggle APPROVAL_API_KEY see warning behaviour
    from app import auth as auth_mod
    auth_mod._warned_open = False

    apr_requests._requests.clear()
    apr_requests._waiters.clear()
    events._subscribers.clear()
    yield
    apr_requests._requests.clear()
    apr_requests._waiters.clear()
    events._subscribers.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
