"""
Deterministic, no-network fallback brain.

Produces valid §3 Diagnosis and §4 Plan without any Lyzr or LLM calls.
Keyword-routes the alert to an incident_type, runbook, and ordered plan.

Public API:
    diagnose_fallback(alert) -> dict   (§3)
    plan_fallback(diagnosis) -> dict   (§4)
    run_fallback(alert, log) -> (dict, dict)
"""
from __future__ import annotations

import re
from typing import Callable

from app.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Routing rules: (keywords, incident_type, runbook, steps, severity)
# Each entry is matched against lower-cased tags + body text.
# First match wins; default is error_spike.
# ---------------------------------------------------------------------------

_RULES: list[tuple[list[str], str, str, list[dict], str]] = [
    (
        ["deploy:", "rollback", "5xx-after-deploy", "immediately after deploy", "after deploy"],
        "bad_deploy",
        "Bad-Deploy-Rollback.md",
        [
            {"action": "rollback_deployment", "autonomy": "auto",  "reversible": True,  "description": "Revert to the last known-good deploy"},
            {"action": "restart_service",      "autonomy": "auto",  "reversible": True,  "description": "Restart workers after rollback"},
            {"action": "isolate_service",      "autonomy": "human", "reversible": True,  "description": "Remove from rotation if rollback fails"},
        ],
        "SEV-2",
    ),
    # Credential/key leak — check before generic security so akia/revoke wins
    (
        ["akia", "credential", "iam", "revok", "leak", "exposed key"],
        "security",
        "AWS-Key-Revocation.md",
        [
            {"action": "revoke_keys", "autonomy": "human", "reversible": False, "description": "Deactivate exposed credentials"},
        ],
        "SEV-2",
    ),
    (
        ["cve", "shellshock", "rce", "exploit", "bash", "cgi", "ransomware", "encrypt", "ransom",
         "edr", "c2", "beacon", "quarantine"],
        "security",
        "CVE-2026-Shellshock-Mitigation.md",
        [
            {"action": "isolate_container", "autonomy": "human", "reversible": True, "description": "Sever container network to stop lateral movement"},
        ],
        "SEV-1",
    ),
    (
        ["5xx", "error rate", "error spike", "5xx spike", "latency"],
        "error_spike",
        "Error-Spike-Mitigation.md",
        [
            {"action": "restart_service",  "autonomy": "auto",  "reversible": True,  "description": "Restart the affected service workers"},
            {"action": "disable_feature",  "autonomy": "auto",  "reversible": True,  "description": "Disable the triggering feature flag"},
            {"action": "isolate_service",  "autonomy": "human", "reversible": True,  "description": "Remove from rotation as last resort"},
        ],
        "SEV-2",
    ),
]

_DEFAULT_RULE = (
    "error_spike",
    "Error-Spike-Mitigation.md",
    [
        {"action": "restart_service",  "autonomy": "auto",  "reversible": True,  "description": "Restart the affected service workers"},
        {"action": "disable_feature",  "autonomy": "auto",  "reversible": True,  "description": "Disable the triggering feature flag"},
        {"action": "isolate_service",  "autonomy": "human", "reversible": True,  "description": "Remove from rotation as last resort"},
    ],
    "SEV-2",
)

_SEVERITY_SPOKEN = {
    "SEV-1": "Severity one",
    "SEV-2": "Severity two",
    "SEV-3": "Severity three",
}

_ACTION_SPOKEN = {
    "rollback_deployment": "rolling back to the previous good deploy",
    "restart_service":     "restarting the service",
    "isolate_service":     "removing the service from rotation",
    "disable_feature":     "disabling the triggering feature flag",
    "isolate_container":   "isolating the container",
    "quarantine_host":     "quarantining the host",
    "revoke_keys":         "revoking the exposed keys",
    "scale_up":            "scaling up capacity",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_tags(tags: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for tag in tags:
        if ":" in tag:
            k, _, v = tag.partition(":")
            result[k.lower()] = v
    return result


def _select_rule(alert: dict) -> tuple[str, str, list[dict], str]:
    haystack = " ".join(alert.get("tags", [])).lower() + " " + alert.get("body", "").lower()
    for keywords, incident_type, runbook, steps, severity in _RULES:
        if any(kw in haystack for kw in keywords):
            return incident_type, runbook, steps, severity
    return _DEFAULT_RULE


def _resolve_service_id(alert: dict) -> str:
    """Return a real server id from the alert, falling back to the first server."""
    from app.state import get_state

    servers = get_state().get("servers", [])
    real_ids = {s["id"] for s in servers}

    tag_map = _parse_tags(alert.get("tags", []))
    host_id = tag_map.get("host") or alert.get("host", "")

    if host_id in real_ids:
        return host_id

    # Try service tag partial match
    service_tag = tag_map.get("service", "")
    for s in servers:
        if service_tag and service_tag in s["id"]:
            return s["id"]

    return servers[0]["id"] if servers else host_id


def _build_script(severity: str, service_id: str, first_action: str, incident_type: str) -> str:
    severity_spoken = _SEVERITY_SPOKEN.get(severity, severity)
    action_spoken = _ACTION_SPOKEN.get(first_action, first_action.replace("_", " "))

    if incident_type == "bad_deploy":
        return (
            f"{severity_spoken}: the {service_id} service is failing after the last deploy. "
            f"I can attempt {action_spoken} immediately. "
            f"Do you approve the rollback?"
        )
    if incident_type == "security":
        return (
            f"{severity_spoken}: a security exploit has been detected on {service_id}. "
            f"The runbook calls for {action_spoken} to stop lateral movement. "
            f"Do you approve?"
        )
    # error_spike and default
    return (
        f"{severity_spoken}: the {service_id} service is experiencing elevated error rates. "
        f"I propose {action_spoken} as the first remediation step. "
        f"Do you approve?"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diagnose_fallback(alert: dict) -> dict:
    """Deterministic §3 Diagnosis. No network."""
    from app.state import blast_radius

    service_id = _resolve_service_id(alert)
    incident_type, runbook, _, severity = _select_rule(alert)

    tag_map = _parse_tags(alert.get("tags", []))
    route = tag_map.get("route", "/")
    deploy_id = tag_map.get("deploy", "")
    cve_tag = tag_map.get("cve")

    blast = blast_radius(service_id)

    exact_location: dict = {
        "service": service_id,
        "route": route,
        "deploy_id": deploy_id,
        "commit": "",
        "datadog_link": "",
    }

    # Infer commit from deployments if available for bad_deploy
    if incident_type == "bad_deploy" and deploy_id:
        try:
            from app.deployments import get_deployment
            dep = get_deployment(service_id)
            if dep and dep.get("current", {}).get("deploy_id") == deploy_id:
                exact_location["commit"] = dep["current"].get("commit", "")
        except Exception:
            pass

    diagnosis: dict = {
        "incident_type": incident_type,
        "severity": severity,
        "affected_service": service_id,
        "exact_location": exact_location,
        "blast_radius": blast,
        "runbook": runbook,
        "confidence": 0.80,
        "summary": alert.get("title", "Incident detected"),
        "rationale": f"Alert tags and body matched the {incident_type} routing rule; runbook {runbook} selected.",
        "cve": cve_tag if incident_type == "security" else None,
    }
    return diagnosis


def plan_fallback(diagnosis: dict) -> dict:
    """Deterministic §4 Plan from a §3 Diagnosis. No network."""
    incident_type = diagnosis.get("incident_type", "error_spike")
    severity = diagnosis.get("severity", "SEV-2")
    service_id = diagnosis.get("affected_service", "unknown")

    # Match by both incident_type and runbook to disambiguate security sub-types
    runbook = diagnosis.get("runbook", "")
    matched_steps = None
    for keywords, itype, rb, steps, sev in _RULES:
        if itype == incident_type and (not runbook or rb == runbook):
            matched_steps = steps
            break
    if matched_steps is None:
        matched_steps = _DEFAULT_RULE[2]

    # Stamp target on every step
    stamped_steps = [{**step, "target": service_id} for step in matched_steps]
    first_action = stamped_steps[0]["action"]

    script = _build_script(severity, service_id, first_action, incident_type)

    plan: dict = {
        "summary": f"Remediation plan for {incident_type} on {service_id}.",
        "steps": stamped_steps,
        "script": script,
    }
    return plan


def run_fallback(alert: dict, log: Callable[[str, str], None]) -> tuple[dict, dict]:
    """Full deterministic brain. Returns (§3 diagnosis, §4 plan)."""
    service_id = _resolve_service_id(alert)
    incident_type, runbook, _, _ = _select_rule(alert)
    log("AGENT", f"[Fallback] Routing: incident_type={incident_type} service={service_id} runbook={runbook}")

    diagnosis = diagnose_fallback(alert)
    plan = plan_fallback(diagnosis)
    return diagnosis, plan
