# The brain — Lyzr Automata 2-agent pipeline

> Scope: the text intelligence that runs *before* any approval channel. Pure function:
> `alert payload → (forensic JSON, commander script)`. Shapes in
> [data-contracts.md](data-contracts.md) §3–4. Voice config is separate — see
> [voice.md](voice.md).

## Why two agents

One agent could do this, but the split is a **demo asset**: the terminal shows two
distinct reasoning steps (diagnose → decide-how-to-say-it), which reads as "the system is
thinking." Keep them separate. They run sequentially (Agent 2 consumes Agent 1).

```
alert ──► Agent 1: Forensic Synthesizer ──(strict JSON)──► Agent 2: Commander ──► script
              │ RAG over runbooks/                              │
              ▼                                                 ▼
        emit [AGENT] logs                               emit [AGENT] logs
```

## Agent 1 — Forensic Synthesizer

**Job:** turn a raw alert into a structured diagnosis grounded in the runbooks.

- **Inputs:** the alert payload + the runbook corpus (`backend/runbooks/*.md`).
- **RAG:** preferred = Lyzr's built-in knowledge base. **Local fallback (PoC-friendly):**
  there are only 3 short runbooks — read them into the prompt directly. Zero infra, fully
  deterministic, no embedding store. Start with the fallback; upgrade to Lyzr KB only if
  it demos better.
- **Output:** strict JSON per data-contracts §3. **No prose, no markdown fences.**

**Prompt skeleton:**
```
You are a SOC forensic analyst. You receive a security alert and a set of runbooks.
Identify: severity, the CVE, the vulnerable server (by id), the blast radius (server ids
that depend on it), the matching runbook, and the single recommended remediation action.
The action MUST be one of: isolate_container | revoke_keys | quarantine_host.
Ground the recommendation in the runbook — cite it in `rationale`.
Return ONLY valid JSON matching this schema: { ...§3... }. No other text.
```

**Guardrails:** if no runbook matches, set `recommended_action` to the safest available
and say so in `rationale`. Never invent a CVE or server id not present in the inputs.

## Agent 2 — Commander (script writer)

**Job:** turn the diagnosis into a short spoken script for the voice agent.

- **Input:** Agent 1's JSON.
- **Output:** Commander object per data-contracts §4.

**Hard constraints (bake in from the first draft — these are the "Day 6" guardrails):**
1. `script` is **≤ 3 sentences**. Time-critical; long scripts kill the demo.
2. It **ends in a yes/no question** naming the action and target.
3. Spoken register: say "Severity one," not "SEV-1"; expand abbreviations; no markdown.
4. Lead with the punch: severity + what's at risk, then the ask.

**Prompt skeleton:**
```
You are the incident commander speaking to an on-call engineer by voice. Given the JSON
diagnosis, write a script of AT MOST three sentences that: states severity and the
at-risk service, states what the runbook recommends, and ends by asking for a yes/no
approval of the specific action. Speak naturally — no jargon codes, no markdown. Return
JSON: { "script": "...", "action": "...", "target": "..." }.
```

**Example output:** see data-contracts §4.

## Pipeline (`brain/pipeline.py`)

```python
def run(alert: dict, log) -> tuple[dict, dict]:
    log("AGENT", f"Parsing alert {alert['alert_id']} — priority {alert['priority']}")
    forensic = forensic_synthesizer(alert, runbooks)      # Agent 1
    log("AGENT", f"Matched runbook {forensic['runbook']}; "
                 f"recommending {forensic['recommended_action']} on {forensic['action_target']}")
    commander = commander_agent(forensic)                 # Agent 2
    log("AGENT", "Drafted approval script.")
    return forensic, commander
```

`log` is injected by the route so each step streams to the UI (see
[backend.md](backend.md)). Keep the pipeline HTTP-free so it's unit-testable.

## Robustness

- **JSON parsing:** Agent 1/2 may wrap JSON in fences or add stray text. Strip and
  `json.loads` defensively; on failure, retry once with a "return JSON only" nudge, then
  fall back to a static diagnosis/script and log a `[SYSTEM]` warning.
- **No Lyzr key:** skip the agents entirely, use the canned script (see backend config).
  The loop must still demo without any paid API.

## Guardrails recap (also Phase 6)

- Script length cap enforced in the Commander prompt **and** re-checked in code (truncate
  + warn if an over-long script slips through).
- Voice-time fallback line ("I do not have that context. Escalating to tier 2.") is a
  **voice-agent** concern, configured in [voice.md](voice.md), not here.
