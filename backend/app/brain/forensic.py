"""
Agent 1 — Forensic Synthesizer (Lyzr Automata path).

Imported lazily by pipeline.py. If lyzr-automata is not installed this module
still imports cleanly; the ImportError surfaces only when run_forensic() is called
with a Lyzr key, which then triggers the fallback.
"""

import json
import re
import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_RUNBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "runbooks"

# §3 required keys
_REQUIRED_KEYS = {
    "severity", "cve", "vulnerable_server", "service",
    "blast_radius", "runbook", "recommended_action", "action_target", "rationale",
}
_VALID_ACTIONS = {"isolate_container", "revoke_keys", "quarantine_host"}


def _load_runbooks() -> str:
    """Read all runbooks into a single string for prompt injection."""
    parts: list[str] = []
    for p in sorted(_RUNBOOKS_DIR.glob("*.md")):
        parts.append(f"=== {p.name} ===\n{p.read_text()}")
    return "\n\n".join(parts)


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences if the model wrapped its output."""
    raw = raw.strip()
    # ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        return match.group(1).strip()
    return raw


def _parse_json(raw: str) -> dict | None:
    cleaned = _strip_fences(raw)
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return None


def _validate(obj: dict) -> bool:
    if not _REQUIRED_KEYS.issubset(obj.keys()):
        return False
    if obj.get("recommended_action") not in _VALID_ACTIONS:
        return False
    if not isinstance(obj.get("blast_radius"), list):
        return False
    return True


def _build_prompt(alert: dict, runbooks: str) -> str:
    return f"""You are a SOC forensic analyst. You receive a security alert and a set of runbooks.

ALERT:
{json.dumps(alert, indent=2)}

RUNBOOKS:
{runbooks}

Identify: severity, the CVE, the vulnerable server (by id from the alert host field), the blast \
radius (server ids that depend on it from depended_on_by in the alert/runbook context), \
the matching runbook filename, and the single recommended remediation action.

The recommended_action MUST be exactly one of: isolate_container | revoke_keys | quarantine_host
Ground the recommendation in the runbook — cite it in `rationale`.

Return ONLY valid JSON with no other text, no markdown fences, matching this exact schema:
{{
  "severity": "SEV-1",
  "cve": "CVE-XXXX-XXXX",
  "vulnerable_server": "<server-id>",
  "service": "<service-name>",
  "blast_radius": ["<server-id>", ...],
  "runbook": "<filename>.md",
  "recommended_action": "isolate_container",
  "action_target": "<server-id>",
  "rationale": "<one sentence citing the runbook>"
}}"""


_JSON_ONLY_NUDGE = "\n\nReturn ONLY the JSON object. No explanation, no markdown fences."


def run_forensic(alert: dict, emit: Callable[[str, str], None]) -> dict:
    """
    Call Lyzr Automata Agent 1.  Raises on unrecoverable failure so the pipeline
    can fall back.  emit is the log callback with signature (source, message).
    """
    from lyzr_automata import AI, LiteLLM  # lazy import — fails cleanly if not installed
    from app.config import LYZR_API_KEY

    runbooks = _load_runbooks()
    prompt = _build_prompt(alert, runbooks)

    emit("AGENT", "Forensic Synthesizer: analysing alert against runbooks…")

    llm = LiteLLM(api_key=LYZR_API_KEY, model="gpt-4o-mini")
    agent = AI(role="SOC forensic analyst", goal="Produce structured JSON diagnosis")

    # First attempt
    raw: str = agent.execute(llm=llm, prompt=prompt)
    obj = _parse_json(raw)

    # Retry with nudge if parsing failed or output is invalid
    if obj is None or not _validate(obj):
        emit("AGENT", "Forensic: JSON parse failed — retrying with nudge…")
        raw2: str = agent.execute(llm=llm, prompt=prompt + _JSON_ONLY_NUDGE)
        obj = _parse_json(raw2)

    if obj is None or not _validate(obj):
        raise ValueError(f"Forensic agent returned unparseable output after retry: {raw!r}")

    return obj
