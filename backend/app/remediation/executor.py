"""
Executor abstraction — data-contracts §4b + remediation.md §Executor toggle.

RemediationExecutor  — Protocol (the interface)
SimulatedExecutor    — default impl; mutates in-memory state only
RealExecutor         — STUB; raises NotImplementedError until a provider adapter is built
get_executor()       — factory; reads EXECUTION_MODE from config
"""
from __future__ import annotations

from typing import Protocol

from app.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol — the only interface the engine ever sees
# ---------------------------------------------------------------------------

class RemediationExecutor(Protocol):
    def run(self, action: str, target: str) -> dict:
        """Execute an action against a target.

        Returns {"ok": bool, "detail": str}.
        """
        ...

    def verify(self, incident: dict, alert: dict) -> bool:
        """Ask whether the alert has cleared after the last attempt."""
        ...


# ---------------------------------------------------------------------------
# SimulatedExecutor — mutates in-memory §2 / §2b state; touches nothing real
# ---------------------------------------------------------------------------

class SimulatedExecutor:
    """
    Simulate-mode behavior per §4b:

    action                   | effect
    -------------------------|-----------------------------------------------
    rollback_deployment      | deployments.rollback(target); state.set_status(target, "rolled_back")
    restart_service          | state.set_status(target, "degraded") then "recovered"; logs both
    isolate_service          | state.set_status(target, "isolated")
    isolate_container        | state.set_status(target, "isolated")
    quarantine_host          | state.set_status(target, "isolated")
    scale_up                 | log only; status unchanged
    disable_feature          | log only; status unchanged
    revoke_keys              | log only; status unchanged
    <unknown>                | {"ok": False, "detail": "unknown action"}
    """

    def run(self, action: str, target: str) -> dict:
        try:
            return self._dispatch(action, target)
        except Exception:
            logger.exception("SimulatedExecutor.run raised for action=%s target=%s", action, target)
            return {"ok": False, "detail": f"executor error on action={action}"}

    def _dispatch(self, action: str, target: str) -> dict:
        if action == "rollback_deployment":
            return self._rollback(target)
        if action == "restart_service":
            return self._restart(target)
        if action in ("isolate_service", "isolate_container", "quarantine_host"):
            return self._isolate(target, action)
        if action == "scale_up":
            logger.info("[SIM] scale_up %s — added capacity (log only)", target)
            return {"ok": True, "detail": f"Scaled up {target} (simulated)"}
        if action == "disable_feature":
            logger.info("[SIM] disable_feature %s — feature flag off (log only)", target)
            return {"ok": True, "detail": f"Feature flag disabled on {target} (simulated)"}
        if action == "revoke_keys":
            logger.info("[SIM] revoke_keys %s — credentials revoked (log only)", target)
            return {"ok": True, "detail": f"Keys revoked for {target} (simulated)"}

        logger.warning("[SIM] Unknown action '%s' for target '%s'", action, target)
        return {"ok": False, "detail": f"Unknown action: {action}"}

    def _rollback(self, target: str) -> dict:
        from app import deployments, state
        new_deploy = deployments.rollback(target)
        state.set_status(target, "rolled_back")
        deploy_id = new_deploy.get("deploy_id", "unknown")
        detail = f"Rolled back {target} to {deploy_id} (simulated)"
        logger.info("[SIM] rollback_deployment %s → %s", target, deploy_id)
        return {"ok": True, "detail": detail}

    def _restart(self, target: str) -> dict:
        from app import state
        state.set_status(target, "degraded")
        logger.info("[SIM] restart_service %s — brief degraded window", target)
        state.set_status(target, "recovered")
        logger.info("[SIM] restart_service %s — recovered", target)
        return {"ok": True, "detail": f"Restarted {target} (simulated)"}

    def _isolate(self, target: str, action: str) -> dict:
        from app import state
        state.set_status(target, "isolated")
        logger.info("[SIM] %s %s → isolated", action, target)
        return {"ok": True, "detail": f"{target} isolated (simulated via {action})"}

    def verify(self, incident: dict, alert: dict) -> bool:
        """Scriptable demo verification.

        If alert contains sim_resolves_after: the alert clears only after the attempt
        whose action matches that value appears in incident["attempts"].
        If sim_resolves_after is absent: resolve after the first auto step (i.e. any attempt
        has been recorded — always return True).
        """
        sim_key = alert.get("sim_resolves_after")
        if sim_key is None:
            # Default: resolve after the first auto step
            return len(incident.get("attempts", [])) > 0

        # Find the action of the last recorded attempt
        attempts = incident.get("attempts", [])
        if not attempts:
            return False
        last_action = attempts[-1].get("action")
        return last_action == sim_key


# ---------------------------------------------------------------------------
# RealExecutor — documented STUB; raises NotImplementedError
# ---------------------------------------------------------------------------

class RealExecutor:
    """
    Future real executor — delegates to a provider adapter.

    Provider adapters live under app/remediation/adapters/. Each adapter
    wraps a single provider (Vercel, Render, Railway, Shell, …) and is
    selected at construction time via the PROVIDER env var. No provider SDK
    may leak outside adapters into the engine, routes, or brain.

    verify() re-queries a Datadog monitor or hits a service health endpoint
    and treats "recovered for N seconds" as cleared.

    To activate: set EXECUTION_MODE=real and supply PROVIDER + provider creds.
    """

    def run(self, action: str, target: str) -> dict:
        raise NotImplementedError(
            "RealExecutor is not implemented. "
            "Set EXECUTION_MODE=simulate or implement a provider adapter."
        )

    def verify(self, incident: dict, alert: dict) -> bool:
        raise NotImplementedError(
            "RealExecutor.verify is not implemented. "
            "Set EXECUTION_MODE=simulate or implement a provider adapter."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_executor() -> RemediationExecutor:
    """Return the executor selected by EXECUTION_MODE (config).

    "simulate" → SimulatedExecutor (default and only real impl)
    "real"     → RealExecutor stub (raises NotImplementedError at call time)
    """
    from app.config import EXECUTION_MODE
    if EXECUTION_MODE == "real":
        logger.warning(
            "EXECUTION_MODE=real: RealExecutor will raise NotImplementedError — "
            "no provider adapter is implemented yet."
        )
        return RealExecutor()
    return SimulatedExecutor()
