"""
Deterministic, no-API fallback brain.

Selected when LYZR_API_KEY is absent or the Lyzr path raises. Does NOT make any
network calls. Returns correctly-shaped §3 (forensic) and §4 (commander) dicts.
"""

import json
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE = Path(__file__).resolve().parent.parent.parent  # backend/
_INFRA_PATH = _BASE / "data" / "infrastructure_state.json"
_RUNBOOKS_DIR = _BASE / "runbooks"

# ---------------------------------------------------------------------------
# Runbook routing rules  (keyword → file, action, severity)
# ---------------------------------------------------------------------------
_RULES: list[tuple[list[str], str, str, str]] = [
    # (keywords_in_tags_or_body, runbook_file, action, severity)
    (
        ["shellshock", "rce", "cve-2026-1337", "cve:cve-2026-1337", "bash", "cgi"],
        "CVE-2026-Shellshock-Mitigation.md",
        "isolate_container",
        "SEV-1",
    ),
    (
        ["akia", "key", "credential", "iam", "aws", "revok", "leak"],
        "AWS-Key-Revocation.md",
        "revoke_keys",
        "SEV-2",
    ),
    (
        ["ransomware", "encrypt", "ransom", "edr", "c2", "beacon"],
        "Ransomware-Containment.md",
        "quarantine_host",
        "SEV-1",
    ),
]
_DEFAULT_RULE = ("CVE-2026-Shellshock-Mitigation.md", "isolate_container", "SEV-1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_infra() -> dict:
    with open(_INFRA_PATH) as f:
        return json.load(f)


def _parse_tags(tags: list[str]) -> dict[str, str]:
    """Extract key:value pairs from Datadog-style tag list."""
    result: dict[str, str] = {}
    for tag in tags:
        if ":" in tag:
            k, _, v = tag.partition(":")
            result[k.lower()] = v
    return result


def _select_rule(alert: dict) -> tuple[str, str, str]:
    """Return (runbook_filename, action, severity) for the alert."""
    # Build a haystack from tags + body (lower-cased)
    tag_text = " ".join(alert.get("tags", [])).lower()
    body_text = alert.get("body", "").lower()
    haystack = tag_text + " " + body_text

    for keywords, runbook, action, severity in _RULES:
        if any(kw in haystack for kw in keywords):
            return runbook, action, severity

    return _DEFAULT_RULE


def _blast_radius(host_id: str, servers: list[dict]) -> list[str]:
    """
    Transitive closure of depended_on_by starting from host_id.

    A server S is in the blast radius if it directly or transitively lists
    host_id in its chain of dependencies (i.e., host_id going down would
    eventually break S).
    """
    # Build an adjacency map: server → set of servers that depend on it
    depends: dict[str, list[str]] = {s["id"]: s.get("depended_on_by", []) for s in servers}

    visited: set[str] = set()
    queue: list[str] = [host_id]

    while queue:
        current = queue.pop()
        for dependent in depends.get(current, []):
            if dependent not in visited:
                visited.add(dependent)
                queue.append(dependent)

    return sorted(visited)


def _get_server(host_id: str, servers: list[dict]) -> dict | None:
    for s in servers:
        if s["id"] == host_id:
            return s
    return None


def _sentences(text: str) -> list[str]:
    """Rough sentence splitter on '. ' and '? '."""
    import re
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return [p for p in parts if p]


_SEVERITY_SPOKEN = {
    "SEV-1": "Severity one",
    "SEV-2": "Severity two",
    "SEV-3": "Severity three",
}

_ACTION_SPOKEN = {
    "isolate_container": "isolating the container",
    "revoke_keys": "revoking the exposed keys",
    "quarantine_host": "quarantining the host",
}

_ACTION_QUESTION = {
    "isolate_container": "isolating the Auth Server container",
    "revoke_keys": "revoking the exposed keys",
    "quarantine_host": "quarantining the host",
}


def _build_script(forensic: dict) -> str:
    severity_spoken = _SEVERITY_SPOKEN.get(forensic["severity"], forensic["severity"])
    action_label = _ACTION_SPOKEN.get(forensic["recommended_action"], forensic["recommended_action"])
    server_name = forensic.get("service", forensic["action_target"])
    blast = forensic.get("blast_radius", [])
    blast_str = " and ".join(blast) if blast else "downstream services"
    target = forensic["action_target"]

    script = (
        f"{severity_spoken} alert: the {server_name} is under active attack with {forensic['cve']}, "
        f"putting {blast_str} at risk. "
        f"The runbook calls for {action_label} immediately. "
        f"Do you approve {action_label} on {target}?"
    )
    return script


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_fallback(alert: dict, log: Callable[[str, str], None]) -> tuple[dict, dict]:
    """
    Pure-Python fallback.  No network.  Always returns valid §3 + §4 shapes.
    """
    infra = _load_infra()
    servers = infra["servers"]

    tag_map = _parse_tags(alert.get("tags", []))
    host_id = tag_map.get("host") or alert.get("host", "")
    cve = tag_map.get("cve", "UNKNOWN-CVE")
    service_tag = tag_map.get("service", "")

    # Resolve to a real server id; fall back to the first server if not found
    server = _get_server(host_id, servers)
    if server is None:
        # Try matching by service tag
        server = next((s for s in servers if service_tag and service_tag in s["id"]), servers[0])
        host_id = server["id"]

    runbook_file, action, severity = _select_rule(alert)
    blast = _blast_radius(host_id, servers)
    service_name = server.get("service", service_tag or host_id)

    log("AGENT", f"[Fallback] Matched runbook {runbook_file} for host {host_id}")

    forensic: dict = {
        "severity": severity,
        "cve": cve,
        "vulnerable_server": host_id,
        "service": service_name,
        "blast_radius": blast,
        "runbook": runbook_file,
        "recommended_action": action,
        "action_target": host_id,
        "rationale": (
            f"Alert body and tags match {runbook_file.replace('.md', '')}. "
            f"Runbook mandates {action} on the vulnerable host to prevent lateral movement."
        ),
    }

    script = _build_script(forensic)

    commander: dict = {
        "script": script,
        "action": action,
        "target": host_id,
    }

    return forensic, commander
