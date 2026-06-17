"""
Tests for app/remediation/executor.py and app/remediation/engine.py.

Coverage targets:
  (1) auto rollback fails + restart succeeds → resolved via restart, attempts recorded
  (2) SEV-1 severity gate → escalates immediately
  (3) first step is human autonomy → escalates immediately
  (4) execute_step approves an action and flips state to resolved
  (5) execute_step idempotency: already-resolved incident → no-op
  (6) SimulatedExecutor unit tests per action
  (7) verify() reads sim_resolves_after correctly

Do NOT import app.main.
"""
from __future__ import annotations

import pytest

from app import incidents as inc_store, state, deployments, events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_alert(**kwargs) -> dict:
    base = {
        "alert_id": "test-alert",
        "title": "Test Alert",
        "alert_type": "reliability",
        "priority": "P1",
        "tags": ["service:payment-gw"],
        "body": "Test alert body.",
        "host": "payment-gw",
        "timestamp": "2026-06-15T09:14:00Z",
    }
    base.update(kwargs)
    return base


def _make_incident(plan_steps: list[dict], severity: str = "SEV-2") -> dict:
    alert = _make_alert()
    inc = inc_store.open_incident(alert, execution_mode="simulate")
    inc_store.set_diagnosis(inc["incident_id"], {
        "incident_type": "bad_deploy",
        "severity": severity,
        "affected_service": "payment-gw",
        "exact_location": {"service": "payment-gw"},
        "blast_radius": [],
        "runbook": "Bad-Deploy-Rollback.md",
        "confidence": 0.9,
        "summary": "Test",
        "rationale": "Test rationale",
        "cve": None,
    })
    inc_store.set_plan(inc["incident_id"], {
        "summary": "Test plan",
        "steps": plan_steps,
        "script": "Do you approve?",
    })
    return inc_store.get_incident(inc["incident_id"])


def _noop_log(source: str, message: str) -> None:
    pass


def _make_log_recorder() -> tuple[list[str], callable]:
    msgs: list[str] = []

    def log(source: str, message: str) -> None:
        msgs.append(message)

    return msgs, log


# ---------------------------------------------------------------------------
# (1) Auto rollback fails, restart succeeds → resolved via restart
# ---------------------------------------------------------------------------

def test_auto_rollback_fails_restart_resolves(monkeypatch):
    """Rollback attempt marked failed by sim_resolves_after; restart clears it."""
    # sim_resolves_after="restart_service" → verify returns False until restart is the last attempt
    alert = _make_alert(sim_resolves_after="restart_service")

    inc = _make_incident([
        {"action": "rollback_deployment", "target": "payment-gw", "autonomy": "auto",
         "reversible": True, "description": "Roll back"},
        {"action": "restart_service",      "target": "payment-gw", "autonomy": "auto",
         "reversible": True, "description": "Restart workers"},
    ], severity="SEV-3")

    escalate_calls: list[dict] = []

    def fake_escalate(incident: dict, log) -> None:
        escalate_calls.append(incident)

    monkeypatch.setattr("app.escalation.escalate", fake_escalate, raising=False)
    # Patch the escalation import inside engine too
    import app.remediation.engine as eng_mod
    import types
    fake_esc_module = types.ModuleType("app.escalation")
    fake_esc_module.escalate = fake_escalate
    monkeypatch.setattr(eng_mod, "_do_escalate", lambda inc, log: (
        fake_escalate(inc, log)
    ) if False else eng_mod._do_escalate.__wrapped__(inc, log) if hasattr(eng_mod._do_escalate, '__wrapped__') else None)

    # Simpler: patch at the import site inside engine._do_escalate
    import sys
    fake_esc = types.ModuleType("app.escalation")
    fake_esc.escalate = fake_escalate
    monkeypatch.setitem(sys.modules, "app.escalation", fake_esc)

    from app.remediation.engine import run_auto_remediation
    msgs, log = _make_log_recorder()
    run_auto_remediation(inc, alert, log)

    final = inc_store.get_incident(inc["incident_id"])
    assert final["status"] == "resolved", f"Expected resolved, got {final['status']}"
    assert len(final["attempts"]) == 2

    actions_tried = [a["action"] for a in final["attempts"]]
    assert actions_tried == ["rollback_deployment", "restart_service"]

    # rollback attempt result: ok=True from SimulatedExecutor, but verify returns False
    # (sim_resolves_after="restart_service" != "rollback_deployment")
    # After restart verify returns True → resolved
    assert final["attempts"][0]["action"] == "rollback_deployment"
    assert final["attempts"][1]["action"] == "restart_service"
    assert final["attempts"][1]["result"] == "succeeded"
    assert len(escalate_calls) == 0, "Should not have escalated"
    log_text = " ".join(msgs)
    assert "auto-resolved" in log_text or "resolved" in log_text


# ---------------------------------------------------------------------------
# (2) SEV-1 severity gate → escalates immediately
# ---------------------------------------------------------------------------

def test_sev1_gate_escalates_immediately(monkeypatch):
    """SEV-1 incident with AUTO_REMEDIATE_MAX_SEVERITY=SEV-2 must escalate, not auto-fix."""
    import sys, types
    escalate_calls: list[dict] = []

    def fake_escalate(incident: dict, log) -> None:
        escalate_calls.append(incident)

    fake_esc = types.ModuleType("app.escalation")
    fake_esc.escalate = fake_escalate
    monkeypatch.setitem(sys.modules, "app.escalation", fake_esc)

    monkeypatch.setattr("app.config.AUTO_REMEDIATE", True)
    monkeypatch.setattr("app.config.AUTO_REMEDIATE_MAX_SEVERITY", "SEV-2")

    alert = _make_alert()
    inc = _make_incident([
        {"action": "rollback_deployment", "target": "payment-gw", "autonomy": "auto",
         "reversible": True, "description": "Roll back"},
    ], severity="SEV-1")

    from app.remediation.engine import run_auto_remediation
    _, log = _make_log_recorder()
    run_auto_remediation(inc, alert, log)

    final = inc_store.get_incident(inc["incident_id"])
    assert final["status"] == "escalated", f"Expected escalated, got {final['status']}"
    assert len(final["attempts"]) == 0, "No attempts should have been made"
    assert len(escalate_calls) == 1


# ---------------------------------------------------------------------------
# (3) First step is human autonomy → escalates immediately
# ---------------------------------------------------------------------------

def test_human_step_escalates_immediately(monkeypatch):
    """First step tagged human → engine stops and escalates without running anything."""
    import sys, types
    escalate_calls: list[dict] = []

    def fake_escalate(incident: dict, log) -> None:
        escalate_calls.append(incident)

    fake_esc = types.ModuleType("app.escalation")
    fake_esc.escalate = fake_escalate
    monkeypatch.setitem(sys.modules, "app.escalation", fake_esc)

    alert = _make_alert()
    inc = _make_incident([
        {"action": "isolate_service", "target": "payment-gw", "autonomy": "human",
         "reversible": True, "description": "Isolate (human required)"},
    ], severity="SEV-3")

    from app.remediation.engine import run_auto_remediation
    msgs, log = _make_log_recorder()
    run_auto_remediation(inc, alert, log)

    final = inc_store.get_incident(inc["incident_id"])
    assert final["status"] == "escalated"
    assert len(final["attempts"]) == 0
    assert len(escalate_calls) == 1
    assert any("human" in m or "approval" in m for m in msgs)


# ---------------------------------------------------------------------------
# (4) execute_step approves an action and flips incident to resolved
# ---------------------------------------------------------------------------

def test_execute_step_resolves_incident():
    """execute_step with a valid action should resolve the incident and update state."""
    alert = _make_alert()
    inc = _make_incident([
        {"action": "rollback_deployment", "target": "payment-gw", "autonomy": "auto",
         "reversible": True, "description": "Roll back"},
    ], severity="SEV-3")

    # Move to awaiting_approval to simulate human-gated flow
    inc_store.set_status(inc["incident_id"], "awaiting_approval")
    inc = inc_store.get_incident(inc["incident_id"])

    from app.remediation.engine import execute_step
    msgs, log = _make_log_recorder()
    updated = execute_step(inc, "rollback_deployment", "payment-gw", "eng-01", log)

    assert updated["status"] == "resolved"
    assert updated["decision"] == "approve"
    assert len(updated["attempts"]) == 1
    assert updated["attempts"][0]["actor"] == "eng-01"
    assert updated["attempts"][0]["action"] == "rollback_deployment"
    assert updated["attempts"][0]["result"] == "succeeded"

    # State should have been mutated
    server = state.get_server("payment-gw")
    assert server["status"] == "rolled_back"


# ---------------------------------------------------------------------------
# (5) execute_step idempotency: already resolved → no-op
# ---------------------------------------------------------------------------

def test_execute_step_idempotent():
    """Calling execute_step on an already-resolved incident must be a no-op."""
    alert = _make_alert()
    inc = _make_incident([
        {"action": "rollback_deployment", "target": "payment-gw", "autonomy": "auto",
         "reversible": True, "description": "Roll back"},
    ], severity="SEV-3")

    inc_store.set_status(inc["incident_id"], "resolved")
    inc = inc_store.get_incident(inc["incident_id"])

    from app.remediation.engine import execute_step
    msgs, log = _make_log_recorder()
    returned = execute_step(inc, "rollback_deployment", "payment-gw", "eng-01", log)

    final = inc_store.get_incident(inc["incident_id"])
    assert final["status"] == "resolved"
    assert len(final["attempts"]) == 0, "No attempts should be added on no-op"
    assert any("no-op" in m or "already resolved" in m for m in msgs)


# ---------------------------------------------------------------------------
# (6) SimulatedExecutor — per-action unit tests
# ---------------------------------------------------------------------------

class TestSimulatedExecutorActions:
    def setup_method(self):
        state._load()
        deployments._load()

    def test_rollback_deployment(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        result = ex.run("rollback_deployment", "payment-gw")
        assert result["ok"] is True
        assert "payment-gw" in result["detail"]
        server = state.get_server("payment-gw")
        assert server["status"] == "rolled_back"
        # deploy swapped
        dep = deployments.get_deployment("payment-gw")
        # previous was dpl_8e1, after rollback it becomes current
        assert dep["current"]["deploy_id"] == "dpl_8e1"

    def test_restart_service(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        result = ex.run("restart_service", "payment-gw")
        assert result["ok"] is True
        server = state.get_server("payment-gw")
        assert server["status"] == "recovered"

    def test_isolate_service(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        result = ex.run("isolate_service", "payment-gw")
        assert result["ok"] is True
        server = state.get_server("payment-gw")
        assert server["status"] == "isolated"

    def test_isolate_container(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        result = ex.run("isolate_container", "payment-gw")
        assert result["ok"] is True
        assert state.get_server("payment-gw")["status"] == "isolated"

    def test_quarantine_host(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        result = ex.run("quarantine_host", "payment-gw")
        assert result["ok"] is True
        assert state.get_server("payment-gw")["status"] == "isolated"

    def test_scale_up_log_only(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        before = state.get_server("payment-gw")["status"]
        result = ex.run("scale_up", "payment-gw")
        assert result["ok"] is True
        assert state.get_server("payment-gw")["status"] == before

    def test_disable_feature_log_only(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        before = state.get_server("payment-gw")["status"]
        result = ex.run("disable_feature", "payment-gw")
        assert result["ok"] is True
        assert state.get_server("payment-gw")["status"] == before

    def test_revoke_keys_log_only(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        before = state.get_server("payment-gw")["status"]
        result = ex.run("revoke_keys", "payment-gw")
        assert result["ok"] is True
        assert state.get_server("payment-gw")["status"] == before

    def test_unknown_action(self):
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        result = ex.run("teleport_server", "payment-gw")
        assert result["ok"] is False
        assert "unknown" in result["detail"].lower()


# ---------------------------------------------------------------------------
# (7) verify() — sim_resolves_after semantics
# ---------------------------------------------------------------------------

class TestSimulatedExecutorVerify:
    def _incident_with_attempts(self, *actions: str) -> dict:
        alert = _make_alert()
        inc = inc_store.open_incident(alert)
        for action in actions:
            inc_store.add_attempt(inc["incident_id"], {
                "action": action,
                "target": "payment-gw",
                "actor": "auto",
                "result": "succeeded",
                "ts": "2026-06-15T09:14:05Z",
            })
        return inc_store.get_incident(inc["incident_id"])

    def test_sim_resolves_after_absent_resolves_after_first_attempt(self):
        """No sim_resolves_after → True as soon as any attempt exists."""
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        alert = _make_alert()  # no sim_resolves_after
        inc_no_attempts = inc_store.get_incident(inc_store.open_incident(alert)["incident_id"])
        assert ex.verify(inc_no_attempts, alert) is False  # no attempts yet

        inc_with_attempt = self._incident_with_attempts("rollback_deployment")
        assert ex.verify(inc_with_attempt, alert) is True

    def test_sim_resolves_after_matches_last_action(self):
        """sim_resolves_after="restart_service" → True only when last attempt is restart_service."""
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        alert = _make_alert(sim_resolves_after="restart_service")

        inc_rollback_only = self._incident_with_attempts("rollback_deployment")
        assert ex.verify(inc_rollback_only, alert) is False

        inc_restart_last = self._incident_with_attempts("rollback_deployment", "restart_service")
        assert ex.verify(inc_restart_last, alert) is True

    def test_sim_resolves_after_no_attempts_is_false(self):
        """Even when sim_resolves_after is set, no attempts → False."""
        from app.remediation.executor import SimulatedExecutor
        ex = SimulatedExecutor()
        alert = _make_alert(sim_resolves_after="restart_service")
        inc = inc_store.get_incident(inc_store.open_incident(alert)["incident_id"])
        assert ex.verify(inc, alert) is False


# ---------------------------------------------------------------------------
# (8) RealExecutor raises NotImplementedError
# ---------------------------------------------------------------------------

def test_real_executor_raises():
    from app.remediation.executor import RealExecutor
    ex = RealExecutor()
    with pytest.raises(NotImplementedError):
        ex.run("rollback_deployment", "payment-gw")
    with pytest.raises(NotImplementedError):
        ex.verify({}, {})


# ---------------------------------------------------------------------------
# (9) get_executor factory respects EXECUTION_MODE
# ---------------------------------------------------------------------------

def test_get_executor_simulate(monkeypatch):
    monkeypatch.setattr("app.config.EXECUTION_MODE", "simulate")
    from app.remediation.executor import get_executor, SimulatedExecutor
    assert isinstance(get_executor(), SimulatedExecutor)


def test_get_executor_real_returns_real_executor(monkeypatch):
    monkeypatch.setattr("app.config.EXECUTION_MODE", "real")
    from app.remediation.executor import get_executor, RealExecutor
    assert isinstance(get_executor(), RealExecutor)
