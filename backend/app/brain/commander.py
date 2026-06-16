"""
Agent 2 — Commander / script writer (Lyzr Automata path).

Turns the §3 forensic dict into a §4 commander dict with a <=3-sentence spoken script.
Imported lazily by pipeline.py.
"""

import json
import re
import logging
from typing import Callable

log = logging.getLogger(__name__)

_VALID_ACTIONS = {"isolate_container", "revoke_keys", "quarantine_host"}
_REQUIRED_KEYS = {"script", "action", "target"}

MAX_SENTENCES = 3


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
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


def _count_sentences(text: str) -> int:
    """Rough sentence count on sentence-ending punctuation."""
    return len(re.findall(r"[.?!](?:\s|$)", text))


def _ends_with_question(text: str) -> bool:
    return text.rstrip().endswith("?")


def _truncate_to_three(text: str) -> str:
    """
    Truncate script to at most 3 sentences.  The last retained sentence is
    always the question (the original prompt asks us to end with one), so we
    keep the last sentence if it is a question and trim middle content.
    """
    # Split on sentence boundaries
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    if len(parts) <= MAX_SENTENCES:
        return text

    # Keep first two and last (the question)
    kept = parts[:MAX_SENTENCES - 1] + [parts[-1]]
    return " ".join(kept)


def _validate(obj: dict) -> bool:
    if not _REQUIRED_KEYS.issubset(obj.keys()):
        return False
    if obj.get("action") not in _VALID_ACTIONS:
        return False
    if not isinstance(obj.get("script"), str) or not obj["script"].strip():
        return False
    return True


def _build_prompt(forensic: dict) -> str:
    return f"""You are the incident commander speaking to an on-call engineer by voice.

Given this JSON diagnosis:
{json.dumps(forensic, indent=2)}

Write a script of AT MOST three sentences that:
1. States the severity and the service at risk (use "Severity one" not "SEV-1"; expand abbreviations).
2. States what the runbook recommends.
3. Ends by asking for a yes/no approval of the specific action on the specific target server id.

Rules:
- No markdown, no jargon codes.
- Spoken register only.
- The last sentence MUST be a yes/no question naming the action and the target.

Return ONLY valid JSON with no other text:
{{"script": "<spoken script>", "action": "<recommended_action>", "target": "<action_target>"}}"""


_JSON_ONLY_NUDGE = "\n\nReturn ONLY the JSON object. No explanation, no markdown fences."


def run_commander(forensic: dict, emit: Callable[[str, str], None]) -> dict:
    """
    Call Lyzr Automata Agent 2.  Raises on unrecoverable failure so the pipeline
    can fall back.  emit is the log callback with signature (source, message).
    """
    from lyzr_automata import AI, LiteLLM  # lazy import
    from app.config import LYZR_API_KEY

    prompt = _build_prompt(forensic)

    emit("AGENT", "Commander: drafting spoken approval script…")

    llm = LiteLLM(api_key=LYZR_API_KEY, model="gpt-4o-mini")
    agent = AI(role="Incident commander", goal="Produce a short spoken approval script as JSON")

    raw: str = agent.execute(llm=llm, prompt=prompt)
    obj = _parse_json(raw)

    if obj is None or not _validate(obj):
        emit("AGENT", "Commander: JSON parse failed — retrying with nudge…")
        raw2: str = agent.execute(llm=llm, prompt=prompt + _JSON_ONLY_NUDGE)
        obj = _parse_json(raw2)

    if obj is None or not _validate(obj):
        raise ValueError(f"Commander agent returned unparseable output after retry: {raw!r}")

    # Hard enforcement: truncate if script exceeds 3 sentences
    script: str = obj["script"]
    count = _count_sentences(script)
    if count > MAX_SENTENCES:
        log.warning(
            "Commander script exceeded %d sentences (%d found) — truncating.",
            MAX_SENTENCES,
            count,
        )
        emit("AGENT", f"[WARN] Script was {count} sentences — truncated to {MAX_SENTENCES}.")
        obj["script"] = _truncate_to_three(script)

    return obj
