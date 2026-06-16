"""The deterministic (no-network) brain. With LYZR_API_KEY unset (see conftest),
run_brain always takes the fallback path, so these lock in the offline behavior."""
from __future__ import annotations

import re

from app.brain.pipeline import run_brain
from app.brain import fallback


def _noop_log(source: str, message: str) -> None:
    pass


def _sentence_count(script: str) -> int:
    return len([p for p in re.split(r"(?<=[.?!])\s+", script.strip()) if p])


def test_shellshock_alert_recommends_isolation(shellshock_alert):
    forensic, commander = run_brain(shellshock_alert, _noop_log)

    assert forensic["recommended_action"] == "isolate_container"
    assert forensic["action_target"] == "auth-01"
    assert forensic["runbook"] == "CVE-2026-Shellshock-Mitigation.md"
    assert forensic["blast_radius"] == ["payment-gw", "web-01"]
    assert commander["action"] == "isolate_container"
    assert commander["target"] == "auth-01"


def test_commander_script_is_short_and_asks_yes_no(shellshock_alert):
    _, commander = run_brain(shellshock_alert, _noop_log)

    assert _sentence_count(commander["script"]) <= 3
    assert commander["script"].rstrip().endswith("?")


def test_severity_is_spoken_not_coded(shellshock_alert):
    _, commander = run_brain(shellshock_alert, _noop_log)

    assert "Severity one" in commander["script"]
    assert "SEV-1" not in commander["script"]


def test_log_callback_is_invoked(shellshock_alert):
    lines: list[tuple[str, str]] = []
    run_brain(shellshock_alert, lambda s, m: lines.append((s, m)))

    assert lines, "expected the brain to emit progress logs"
    assert any(src == "AGENT" for src, _ in lines)


def test_routing_aws_key_alert_to_revoke():
    alert = {
        "alert_id": "dd-1", "title": "Leaked key", "alert_type": "security", "priority": "P2",
        "tags": ["service:auth", "host:auth-01"],
        "body": "Exposed AKIA credential detected in public repo.",
        "host": "auth-01", "timestamp": "2026-06-15T00:00:00Z",
    }

    forensic, commander = run_brain(alert, _noop_log)

    assert forensic["recommended_action"] == "revoke_keys"
    assert commander["action"] == "revoke_keys"


def test_routing_ransomware_alert_to_quarantine():
    alert = {
        "alert_id": "dd-2", "title": "Ransomware", "alert_type": "security", "priority": "P1",
        "tags": ["service:db", "host:db-01"],
        "body": "EDR detected mass file encryption consistent with ransomware.",
        "host": "db-01", "timestamp": "2026-06-15T00:00:00Z",
    }

    forensic, commander = run_brain(alert, _noop_log)

    assert forensic["recommended_action"] == "quarantine_host"
    assert forensic["action_target"] == "db-01"


def test_unknown_host_falls_back_to_a_real_server(shellshock_alert):
    alert = {**shellshock_alert, "host": "ghost-99", "tags": ["cve:CVE-2026-1337"]}

    forensic, _ = run_brain(alert, _noop_log)

    real_ids = {"auth-01", "payment-gw", "web-01", "db-01"}
    assert forensic["action_target"] in real_ids


def test_action_is_always_a_known_enum(shellshock_alert):
    forensic, _ = run_brain(shellshock_alert, _noop_log)

    assert forensic["recommended_action"] in {"isolate_container", "revoke_keys", "quarantine_host"}


def test_run_brain_falls_back_when_lyzr_path_raises(shellshock_alert, monkeypatch):
    # With a key present, the Lyzr path is attempted; if it throws, the brain
    # must degrade to the deterministic fallback rather than propagate.
    import app.brain.pipeline as pipeline

    monkeypatch.setenv("LYZR_API_KEY", "fake-key")

    def boom(alert, log):
        raise RuntimeError("lyzr exploded")

    monkeypatch.setattr(pipeline, "_run_lyzr", boom)

    forensic, commander = run_brain(shellshock_alert, _noop_log)

    assert forensic["recommended_action"] == "isolate_container"
    assert commander["target"] == "auth-01"
