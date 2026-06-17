# The brain — Lyzr Studio agents (Diagnostician + Strategist)

> Scope: the intelligence that runs *before* any remediation or approval. Pure function:
> `alert → (diagnosis, plan)`. Shapes in [data-contracts.md](data-contracts.md) §3–4. The
> engine that *acts* on the plan is [remediation.md](remediation.md); voice is [voice.md](voice.md).

> **Hosting decision (user-chosen): all agents live in Lyzr Studio.** The two brain agents
> are configured **in the Lyzr Studio UI** and called by the backend over the **Lyzr Agent API**
> (HTTP). The deterministic fallback keeps the demo runnable with zero Lyzr calls.
>
> *(Supersedes the earlier Lyzr Automata + LiteLLM/OpenAI approach. The v1 code in
> `brain/forensic.py` / `commander.py` is replaced by the thin Agent-API client; drop
> `lyzr-automata`.)*

## The three Studio agents at a glance

| Studio agent | This doc | Called via | Output |
|---|---|---|---|
| Diagnostician | here (Agent 1) | Agent API `/v3/inference/chat/` | Diagnosis §3 |
| Strategist | here (Agent 2) | Agent API `/v3/inference/chat/` | Plan + script §4 |
| Voice Agent | [voice.md](voice.md) | Studio voice runtime + `resolve_incident` tool | `/execute` |

All three live in the **same Lyzr Studio account**. The backend authenticates with one
`LYZR_API_KEY` (the Studio `x-api-key`) and addresses each agent by its **agent id**.

## Why two agents

The split is a **demo asset**: the terminal shows two distinct reasoning steps (diagnose →
plan), which reads as "the system is thinking." They run sequentially — the Strategist
consumes the Diagnostician's JSON.

```
alert ──► Studio Agent 1: Diagnostician ──(strict JSON §3)──► Studio Agent 2: Strategist ──► plan + script (§4)
              │ KB: runbooks (in Studio)
              ▼
        emit [AGENT] logs
```

## How the backend calls a Studio agent

One thin client, `app/integrations/lyzr.py`:

```python
def call_agent(agent_id: str, message: str, session_id: str) -> str:
    # POST https://agent-prod.studio.lyzr.ai/v3/inference/chat/
    # headers: { "x-api-key": LYZR_API_KEY, "Content-Type": "application/json" }
    # body:    { "user_id": "callsign", "agent_id": agent_id,
    #            "session_id": session_id, "message": message }
    # returns: the agent's text reply (response["response"])
```

The **system prompt, model, knowledge base, and output schema live in Studio**. The backend
only sends the `message` and parses the reply. `session_id = incident_id` keeps each
incident's two calls coherent.

---

## Agent 1 — Diagnostician

### Studio configuration

**Name:** `Diagnostician`

**Description:**
`SRE/SOC analyst that classifies incidents and maps their exact location and blast radius from alert data and runbooks.`

**Model:** `gpt-4o` (or any capable model available on your Lyzr plan)

**Agent Role:**
`You are a senior SRE/SOC analyst responsible for classifying incidents and pinpointing their exact location in the infrastructure.`

**Agent Goal:**
`Analyse the incoming alert and produce a precise, evidence-grounded diagnosis that the Strategist can act on immediately.`

**Agent Instructions:**
```
You receive a JSON message containing three parts:
1. An incident alert (fields: alert_id, title, alert_type, priority, tags, body, host, timestamp).
2. A compact service map: each entry has id, depended_on_by (who breaks if this service fails).
3. The relevant deployment record (service, current deploy, previous deploy) when a deploy tag is present.

Your knowledge base contains runbooks. Match the alert to the correct runbook before producing output.

CLASSIFY the incident_type as exactly one of:
  security | bad_deploy | error_spike | latency | crash_loop | resource_exhaustion

IDENTIFY the exact_location:
  - service: the affected service id (from the alert's service: tag or host field)
  - route: from the route: tag
  - deploy_id: from the deploy: tag (null if absent)
  - commit: from the deployment record (null if absent)
  - datadog_link: from the alert body if present (null otherwise)

SCOPE the blast_radius: list every service id in depended_on_by transitively from the affected service.

MATCH the runbook: return the filename (e.g. "Bad-Deploy-Rollback.md"). Ground every claim in the alert + runbook. Never invent ids, CVEs, or deploy ids not present in the input.

SET confidence 0–1. If below 0.5, still return the best-effort diagnosis — the fallback engine will override it.

cve: non-null only when incident_type is "security" and a cve: tag is present.

OUTPUT RULES:
- Return ONLY valid JSON matching the structured output schema. No prose, no markdown fences, no explanation.
- If you cannot parse the input, return incident_type "error_spike", confidence 0, and summarise the parse failure in rationale.
```

**Knowledge Base:** Upload all five files from `backend/runbooks/txt/` as a KB attached to this agent (use the `.txt` copies — Lyzr Studio does not accept `.md`):
- `Bad-Deploy-Rollback.txt`
- `Error-Spike-Mitigation.txt`
- `CVE-2026-Shellshock-Mitigation.txt`
- `AWS-Key-Revocation.txt`
- `Ransomware-Containment.txt`

**Structured Output (JSON):** Enable. Paste this into the JSON schema field:

```json
{
  "name": "diagnosis",
  "strict": true,
  "schema": {
    "type": "object",
    "required": ["incident_type", "severity", "affected_service", "exact_location", "blast_radius", "runbook", "confidence", "summary", "rationale", "cve"],
    "additionalProperties": false,
    "properties": {
      "incident_type":    { "type": "string", "enum": ["security", "bad_deploy", "error_spike", "latency", "crash_loop", "resource_exhaustion"] },
      "severity":         { "type": "string", "enum": ["SEV-1", "SEV-2", "SEV-3"] },
      "affected_service": { "type": "string" },
      "exact_location": {
        "type": "object",
        "required": ["service", "route", "deploy_id", "commit", "datadog_link"],
        "additionalProperties": false,
        "properties": {
          "service":      { "type": "string" },
          "route":        { "type": ["string", "null"] },
          "deploy_id":    { "type": ["string", "null"] },
          "commit":       { "type": ["string", "null"] },
          "datadog_link": { "type": ["string", "null"] }
        }
      },
      "blast_radius": { "type": "array", "items": { "type": "string" } },
      "runbook":      { "type": "string" },
      "confidence":   { "type": "number", "minimum": 0, "maximum": 1 },
      "summary":      { "type": "string" },
      "rationale":    { "type": "string" },
      "cve":          { "type": ["string", "null"] }
    }
  }
}
```

**Tools / Skills / Memory:** None. The agent reasons only from the message and its KB.

---

## Agent 2 — Strategist

### Studio configuration

**Name:** `Strategist`

**Description:**
`Incident strategist that turns a diagnosis into an ordered remediation plan and a spoken approval script for the on-call engineer.`

**Model:** `gpt-4o` (same as Diagnostician)

**Agent Role:**
`You are the incident strategist responsible for converting a confirmed diagnosis into a safe, ordered remediation plan.`

**Agent Goal:**
`Produce a prioritised sequence of actions the system can attempt automatically or escalate to a human, plus a concise spoken script to get approval.`

**Agent Instructions:**
```
You receive a JSON message containing:
1. The Diagnostician's diagnosis JSON (incident_type, severity, affected_service, exact_location, blast_radius, runbook, summary).
2. The matched runbook text (if available).

PRODUCE an ordered steps array. Work through the runbook's recommended mitigation sequence in order. For each step:
  - action: one of rollback_deployment | restart_service | isolate_service | scale_up | disable_feature | isolate_container | quarantine_host | revoke_keys
  - target: the affected service id from the diagnosis (or the specific host/container id for security actions)
  - autonomy: "auto" ONLY if the step is both safe AND reversible; otherwise "human"
  - reversible: true or false
  - description: one sentence explaining what this step does

AUTONOMY RULES:
- Default to "human" when in doubt. The system will only auto-run "auto" steps.
- "isolate_service", "quarantine_host", and "revoke_keys" are always "human" — they have customer-facing impact.
- "rollback_deployment", "restart_service", "disable_feature", "scale_up" may be "auto" when the runbook confirms they are safe and reversible.
- SEV-1 incidents: mark the first step "human" unless the runbook explicitly states it is safe.

WRITE the script:
- At most 3 sentences.
- Sentence 1: severity + what is broken + user impact (spoken register: "Severity one", not "SEV-1").
- Sentence 2: what the system already attempted (if steps before this are "auto"), or the proposed first action.
- Sentence 3: a yes/no question asking for approval.
- No markdown, no jargon acronyms, no fences. Natural spoken English only.

OUTPUT RULES:
- Return ONLY valid JSON matching the structured output schema. No prose, no markdown fences.
```

**Knowledge Base:** None. The runbook text is passed in the message by the backend.

**Structured Output (JSON):** Enable. Paste this into the JSON schema field:

```json
{
  "name": "remediation_plan",
  "strict": true,
  "schema": {
    "type": "object",
    "required": ["summary", "steps", "script"],
    "additionalProperties": false,
    "properties": {
      "summary": { "type": "string" },
      "steps": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["action", "target", "autonomy", "reversible", "description"],
          "additionalProperties": false,
          "properties": {
            "action":      { "type": "string", "enum": ["rollback_deployment", "restart_service", "isolate_service", "scale_up", "disable_feature", "isolate_container", "quarantine_host", "revoke_keys"] },
            "target":      { "type": "string" },
            "autonomy":    { "type": "string", "enum": ["auto", "human"] },
            "reversible":  { "type": "boolean" },
            "description": { "type": "string" }
          }
        }
      },
      "script": { "type": "string" }
    }
  }
}
```

**Tools / Skills / Memory:** None.

---

## Pipeline (`brain/pipeline.py`)

```python
def run_brain(alert: dict, log) -> tuple[dict, dict]:
    log("AGENT", f"Diagnosing alert {alert['alert_id']} — priority {alert['priority']}")
    diagnosis = diagnostician(alert, log)      # Agent 1 → §3  (Studio Agent API + parse, or fallback)
    log("AGENT", f"{diagnosis['incident_type']} on {diagnosis['affected_service']} "
                 f"@ {diagnosis['exact_location']['route']}; runbook {diagnosis['runbook']}")
    plan = strategist(diagnosis, log)          # Agent 2 → §4
    log("AGENT", f"Planned {len(plan['steps'])} step(s); first = {plan['steps'][0]['action']}.")
    return diagnosis, plan
```

`diagnostician()` / `strategist()` each call `lyzr.call_agent(...)`, then parse + validate
the reply. Signature unchanged from v1 (`run_brain(alert, log) -> (dict, dict)`), so routes
and the remediation engine are unaffected. Keep the pipeline HTTP-free of *our* API and
unit-testable by mocking `call_agent`.

## Robustness

- **JSON parsing:** the Studio reply is text; strip fences, `json.loads` defensively; on
  failure retry once (re-send with "return JSON only" appended), then fall back to the
  deterministic engine + a `[SYSTEM]` warning.
- **No key / API error / non-2xx:** if `LYZR_API_KEY` is unset or the Agent API errors,
  use the deterministic fallback (rule-based runbook match + templated §3/§4). The loop
  must still demo with zero Lyzr calls.

## Config

`LYZR_API_KEY` (Studio x-api-key), `LYZR_DIAGNOSTICIAN_AGENT_ID`, `LYZR_STRATEGIST_AGENT_ID`,
`LYZR_API_BASE` (default `https://agent-prod.studio.lyzr.ai`). All in `.env` (gitignored).

## Guardrails

- Script length cap stated in the Agent Instructions **and** re-checked in code (truncate + warn).
- The `auto` vs `human` tagging is the **autonomy contract** the engine trusts — err toward `human`.
  Policy enforcement lives in [remediation.md](remediation.md).
- Voice fallback line is a voice-agent concern in [voice.md](voice.md), not here.
