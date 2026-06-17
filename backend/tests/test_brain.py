"""
Brain tests — covers fallback path (no LYZR_API_KEY) and Lyzr-path
parse/retry/fallback-on-error via call_agent mocking.

Run from backend/: .venv/bin/python -m pytest tests/test_brain.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

# Do NOT import app.main — routes are mid-refactor
from app.brain.pipeline import run_brain
from app.brain import fallback as fallback_mod

_ALERTS_DIR = Path(__file__).resolve().parent.parent / "data" / "mock_alerts"


def _load(name: str) -> dict:
    with open(_ALERTS_DIR / name) as f:
        return json.load(f)


def _noop_log(source: str, message: str) -> None:
    pass


def _sentence_count(text: str) -> int:
    return len([p for p in re.split(r"(?<=[.?!])\s+", text.strip()) if p])


# ---------------------------------------------------------------------------
# Fixtures (LYZR_API_KEY is deleted by conftest autouse fixture, so these
# always exercise the deterministic fallback unless we monkeypatch it back in)
# ---------------------------------------------------------------------------

@pytest.fixture
def bad_deploy_alert() -> dict:
    return _load("bad_deploy.json")


@pytest.fixture
def error_spike_alert() -> dict:
    return _load("error_spike.json")


@pytest.fixture
def shellshock_alert() -> dict:
    return _load("shellshock.json")


# ---------------------------------------------------------------------------
# Fallback: bad_deploy.json
# ---------------------------------------------------------------------------

def test_bad_deploy_incident_type(bad_deploy_alert):
    diagnosis, _ = run_brain(bad_deploy_alert, _noop_log)
    assert diagnosis["incident_type"] == "bad_deploy"


def test_bad_deploy_first_step(bad_deploy_alert):
    _, plan = run_brain(bad_deploy_alert, _noop_log)
    first = plan["steps"][0]
    assert first["action"] == "rollback_deployment"
    assert first["autonomy"] == "auto"


def test_bad_deploy_script(bad_deploy_alert):
    _, plan = run_brain(bad_deploy_alert, _noop_log)
    script = plan["script"]
    assert _sentence_count(script) <= 3
    assert script.rstrip().endswith("?")


def test_bad_deploy_script_spoken_severity(bad_deploy_alert):
    _, plan = run_brain(bad_deploy_alert, _noop_log)
    assert "Severity" in plan["script"]
    assert "SEV-" not in plan["script"]


# ---------------------------------------------------------------------------
# Fallback: error_spike.json
# ---------------------------------------------------------------------------

def test_error_spike_incident_type(error_spike_alert):
    diagnosis, _ = run_brain(error_spike_alert, _noop_log)
    assert diagnosis["incident_type"] == "error_spike"


def test_error_spike_first_step(error_spike_alert):
    _, plan = run_brain(error_spike_alert, _noop_log)
    first = plan["steps"][0]
    assert first["action"] == "restart_service"
    assert first["autonomy"] == "auto"


def test_error_spike_script(error_spike_alert):
    _, plan = run_brain(error_spike_alert, _noop_log)
    script = plan["script"]
    assert _sentence_count(script) <= 3
    assert script.rstrip().endswith("?")


# ---------------------------------------------------------------------------
# Fallback: shellshock.json
# ---------------------------------------------------------------------------

def test_shellshock_incident_type(shellshock_alert):
    diagnosis, _ = run_brain(shellshock_alert, _noop_log)
    assert diagnosis["incident_type"] == "security"


def test_shellshock_first_step(shellshock_alert):
    _, plan = run_brain(shellshock_alert, _noop_log)
    first = plan["steps"][0]
    assert first["action"] == "isolate_container"
    assert first["autonomy"] == "human"


def test_shellshock_script(shellshock_alert):
    _, plan = run_brain(shellshock_alert, _noop_log)
    script = plan["script"]
    assert _sentence_count(script) <= 3
    assert script.rstrip().endswith("?")


def test_shellshock_script_spoken_severity(shellshock_alert):
    _, plan = run_brain(shellshock_alert, _noop_log)
    assert "Severity one" in plan["script"]
    assert "SEV-1" not in plan["script"]


# ---------------------------------------------------------------------------
# Shape validation: §3 and §4 required keys present
# ---------------------------------------------------------------------------

_DIAGNOSIS_KEYS = {
    "incident_type", "severity", "affected_service", "exact_location",
    "blast_radius", "runbook", "confidence", "summary", "rationale",
}
_PLAN_KEYS = {"summary", "steps", "script"}
_STEP_KEYS = {"action", "target", "autonomy", "reversible", "description"}


@pytest.mark.parametrize("fixture_name", ["bad_deploy.json", "error_spike.json", "shellshock.json"])
def test_run_brain_returns_valid_shapes(fixture_name):
    alert = _load(fixture_name)
    diagnosis, plan = run_brain(alert, _noop_log)

    assert _DIAGNOSIS_KEYS.issubset(diagnosis.keys()), f"diagnosis missing keys: {_DIAGNOSIS_KEYS - diagnosis.keys()}"
    assert isinstance(diagnosis["blast_radius"], list)
    assert isinstance(diagnosis["exact_location"], dict)

    assert _PLAN_KEYS.issubset(plan.keys()), f"plan missing keys: {_PLAN_KEYS - plan.keys()}"
    assert isinstance(plan["steps"], list) and plan["steps"]
    for step in plan["steps"]:
        assert _STEP_KEYS.issubset(step.keys()), f"step missing keys: {_STEP_KEYS - step.keys()}"


# ---------------------------------------------------------------------------
# Log callback is invoked with AGENT source
# ---------------------------------------------------------------------------

def test_log_callback_invoked(shellshock_alert):
    lines: list[tuple[str, str]] = []
    run_brain(shellshock_alert, lambda s, m: lines.append((s, m)))
    assert lines
    assert any(src == "AGENT" for src, _ in lines)


# ---------------------------------------------------------------------------
# Lyzr path: parse success
# ---------------------------------------------------------------------------

_GOOD_DIAGNOSIS = {
    "incident_type": "security",
    "severity": "SEV-1",
    "affected_service": "auth-01",
    "exact_location": {"service": "auth-01", "route": "/", "deploy_id": "", "commit": "", "datadog_link": ""},
    "blast_radius": ["payment-gw", "web-01"],
    "runbook": "CVE-2026-Shellshock-Mitigation.md",
    "confidence": 0.9,
    "summary": "RCE on auth-01.",
    "rationale": "Matches shellshock pattern.",
    "cve": "CVE-2026-1337",
}

_GOOD_PLAN = {
    "summary": "Isolate container.",
    "steps": [
        {"action": "isolate_container", "target": "auth-01", "autonomy": "human", "reversible": True, "description": "Sever network"},
    ],
    "script": "Severity one: auth-01 is under attack. I can isolate the container. Do you approve?",
}


def test_lyzr_path_parse_success(shellshock_alert, monkeypatch):
    monkeypatch.setenv("LYZR_API_KEY", "fake-key")
    monkeypatch.setenv("LYZR_DIAGNOSTICIAN_AGENT_ID", "diag-agent")
    monkeypatch.setenv("LYZR_STRATEGIST_AGENT_ID", "strat-agent")

    # Reload config values after monkeypatching env
    import app.config as cfg
    monkeypatch.setattr(cfg, "LYZR_API_KEY", "fake-key")
    monkeypatch.setattr(cfg, "LYZR_DIAGNOSTICIAN_AGENT_ID", "diag-agent")
    monkeypatch.setattr(cfg, "LYZR_STRATEGIST_AGENT_ID", "strat-agent")

    call_responses = [json.dumps(_GOOD_DIAGNOSIS), json.dumps(_GOOD_PLAN)]

    with patch("app.integrations.lyzr.call_agent", side_effect=call_responses):
        diagnosis, plan = run_brain(shellshock_alert, _noop_log)

    assert diagnosis["incident_type"] == "security"
    assert plan["steps"][0]["action"] == "isolate_container"


# ---------------------------------------------------------------------------
# Lyzr path: retry then fallback on bad JSON
# ---------------------------------------------------------------------------

def test_lyzr_path_retry_then_fallback(shellshock_alert, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "LYZR_API_KEY", "fake-key")
    monkeypatch.setattr(cfg, "LYZR_DIAGNOSTICIAN_AGENT_ID", "diag-agent")
    monkeypatch.setattr(cfg, "LYZR_STRATEGIST_AGENT_ID", "strat-agent")

    # Both calls return garbage → diagnostician raises → pipeline falls back
    with patch("app.integrations.lyzr.call_agent", return_value="not json at all"):
        diagnosis, plan = run_brain(shellshock_alert, _noop_log)

    # Must still return valid shapes via fallback
    assert diagnosis["incident_type"] in {"security", "bad_deploy", "error_spike", "latency", "crash_loop", "resource_exhaustion"}
    assert plan["steps"]


# ---------------------------------------------------------------------------
# Lyzr path: call_agent raises → fallback
# ---------------------------------------------------------------------------

def test_lyzr_path_error_falls_back(shellshock_alert, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "LYZR_API_KEY", "fake-key")
    monkeypatch.setattr(cfg, "LYZR_DIAGNOSTICIAN_AGENT_ID", "diag-agent")
    monkeypatch.setattr(cfg, "LYZR_STRATEGIST_AGENT_ID", "strat-agent")

    with patch("app.integrations.lyzr.call_agent", side_effect=RuntimeError("network down")):
        diagnosis, plan = run_brain(shellshock_alert, _noop_log)

    # Must return valid shapes via fallback, not raise
    assert diagnosis["incident_type"] == "security"
    assert plan["steps"][0]["action"] == "isolate_container"


# ---------------------------------------------------------------------------
# diagnose_fallback / plan_fallback public API
# ---------------------------------------------------------------------------

def test_diagnose_fallback_direct(shellshock_alert):
    diagnosis = fallback_mod.diagnose_fallback(shellshock_alert)
    assert diagnosis["incident_type"] == "security"
    assert "affected_service" in diagnosis
    assert isinstance(diagnosis["blast_radius"], list)


def test_plan_fallback_direct(shellshock_alert):
    diagnosis = fallback_mod.diagnose_fallback(shellshock_alert)
    plan = fallback_mod.plan_fallback(diagnosis)
    assert plan["steps"]
    assert plan["script"].rstrip().endswith("?")
    assert _sentence_count(plan["script"]) <= 3
