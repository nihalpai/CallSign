"""
Deployments registry (data-contracts §2b).

Loaded once at import from DEPLOYMENTS_PATH into memory; mutated in place.
rollback() swaps current↔previous for a service.
Callers (the remediation executor) are responsible for emitting state events.
"""
from __future__ import annotations
import json
from app.config import DEPLOYMENTS_PATH
from app.logging_config import get_logger

logger = get_logger(__name__)

# Module-level in-memory deployments — list of dicts keyed by "service"
_deployments: list[dict] = []


def _load() -> None:
    global _deployments
    try:
        with open(DEPLOYMENTS_PATH) as f:
            data = json.load(f)
        _deployments = data.get("deployments", [])
        logger.info("Loaded %d deployments from %s", len(_deployments), DEPLOYMENTS_PATH)
    except Exception:
        logger.exception("Failed to load deployments from %s", DEPLOYMENTS_PATH)
        _deployments = []


_load()


def get_deployments() -> list[dict]:
    """Return all deployment records (shallow copy of the list)."""
    return list(_deployments)


def get_deployment(service: str) -> dict | None:
    """Return the full deployment record for a service, or None."""
    for d in _deployments:
        if d["service"] == service:
            return d
    return None


def current_deploy(service: str) -> dict:
    """Return the current deploy snapshot for a service.
    Raises KeyError if the service is not found.
    """
    dep = get_deployment(service)
    if dep is None:
        raise KeyError(f"No deployment record for service '{service}'")
    return dep["current"]


def rollback(service: str) -> dict:
    """Swap current↔previous in memory; return the new current deploy snapshot.

    No-op (with WARNING) if the service is unknown or has no previous deploy.
    """
    dep = get_deployment(service)
    if dep is None:
        logger.warning("rollback: unknown service '%s' — no-op", service)
        return {}

    previous = dep.get("previous")
    if not previous:
        logger.warning("rollback: service '%s' has no previous deploy — no-op", service)
        return dep.get("current", {})

    old_current = dep["current"]
    dep["current"] = previous
    dep["previous"] = old_current
    logger.info(
        "Rolled back '%s': %s → %s",
        service,
        old_current.get("deploy_id"),
        dep["current"].get("deploy_id"),
    )
    return dep["current"]
