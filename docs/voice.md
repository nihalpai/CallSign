# Voice / Escalation Agent (Lyzr Studio)

> Scope: the escalation agent that delivers the Strategist's `script`
> ([data-contracts.md](data-contracts.md) §4) to the on-call engineer and captures their
> approve/deny decision. Currently configured as a **text agent** (voice premium not yet
> active). Slack is the primary approval channel while voice is unavailable —
> see [slack.md](slack.md). The agent, tool, and `/execute` contract are identical across
> all tiers; upgrading to voice is a Studio toggle, not a code change.

> **All three agents live in one Lyzr Studio account** — the two brain agents
> ([agents.md](agents.md), called via the Agent API) and this agent share the same
> `LYZR_API_KEY`. Referenced by `LYZR_VOICE_AGENT_ID`.

## Approval channel tiers

| Tier | Channel | Status |
|------|---------|--------|
| **0** | UI button → `/execute` | ✅ built |
| **1** | Slack DM — incident card with Approve/Deny buttons → `/execute` | ✅ active (primary) |
| **2** | Lyzr Studio text agent → `resolve_incident` tool → `/execute` | ✅ configured, pending voice premium |
| **3** | Lyzr Studio voice agent (browser mic) → `resolve_incident` → `/execute` | future — enable when voice premium available |
| **4** | Real outbound phone call (Twilio + Deepgram/ElevenLabs) | future |

All tiers POST the **same** `/execute` (§6). Nothing downstream knows which tier fired.

---

## Tier 2 — Lyzr Studio text agent (current configuration)

Configured as a standard text agent. When voice premium is enabled, the only change is
toggling the Voice Agent feature on in Studio — the role, goal, instructions, and tool
stay identical.

### Studio configuration

**Name:** `CallSign Voice`

**Description:**
`Emergency incident response agent that delivers a pre-written incident script to the on-call engineer and captures their approve or deny decision.`

**Model:** `gpt-4o` (or the most capable model on your plan — this agent must follow instructions precisely)

**Agent Role:**
`You are an emergency incident response agent that delivers a pre-written script to an on-call engineer and captures their approval decision.`

**Agent Goal:**
`Present the incident script exactly as provided, capture a clear yes or no from the engineer, and call the resolve_incident tool with their decision.`

**Agent Instructions:**
```
You are operating in an emergency incident response scenario. An incident is active and you have been given a script to deliver to the on-call engineer.

OPENING:
- Do not wait for the engineer to initiate. Immediately present the script field from your context exactly as written. Do not paraphrase or summarise it.
- The script is at most 3 sentences and ends in a yes/no question. Deliver it verbatim.

CAPTURING THE DECISION:
- After presenting the script, wait for the engineer's response.
- Accept "yes", "approve", "go ahead", "do it", "confirm" as an APPROVE decision.
- Accept "no", "deny", "stop", "don't", "hold off", "cancel" as a DENY decision.
- If the response is ambiguous, ask once: "Just to confirm — do you approve the action, yes or no?"
- After one clarification attempt, if still ambiguous, treat it as DENY and log it.

CALLING THE TOOL:
- Once you have a clear decision, immediately call the resolve_incident tool with:
    - incident_id: from your context
    - decision: "approve" or "deny"
    - action: from your context
    - target: from your context
    - actor: "voice"
- Do not describe what the tool does. Confirm to the engineer: "Got it. I've logged your decision."

OUT-OF-SCOPE QUESTIONS:
- If the engineer asks anything outside of approving or denying this specific action, say exactly:
  "I don't have that context right now. Please use the CallSign UI or Slack to respond."
  Do not improvise, explain the system, or discuss other incidents.

AFTER THE TOOL CALL:
- Say: "Thank you. The team has been notified." Then end the conversation.
- Do not continue after the tool call completes.

TONE: Direct, calm, professional. This is an emergency channel — be clear and brief, not warm or chatty.
```

**Knowledge Base / Memory / all other features:** Off.

### The custom tool: `resolve_incident`

Add this as an HTTP tool on the agent in Studio:

```
Tool name:    resolve_incident
Description: Call this when the engineer has given a clear approve or deny decision.
             Posts the decision to the CallSign backend and completes the incident
             approval loop.
Method:       POST
URL:          {PUBLIC_BACKEND_URL}/execute
Headers:      Content-Type: application/json
Body (JSON):
  {
    "incident_id": "<from context>",
    "decision":    "approve|deny",
    "action":      "<from context>",
    "target":      "<from context>",
    "actor":       "voice"
  }
```

| Parameter | Source |
|---|---|
| `incident_id` | injected at call-time |
| `decision` | captured from the engineer's response |
| `action` | injected at call-time |
| `target` | injected at call-time |
| `actor` | always the literal string `"voice"` |

### Per-incident context injection — OPEN RISK

The agent needs `script`, `incident_id`, `action`, and `target` at conversation start.
Confirm one of these with Lyzr Studio before activating Tier 2:

1. **Per-call system-prompt injection** (ideal): pass the four fields when triggering the agent via the API.
2. **Input variables / metadata**: injected into the tool call at trigger time.
3. **Fallback**: agent's first turn calls `GET /incident/{id}` to fetch its own context.

### Reachability

The `resolve_incident` tool calls your backend, so it must be publicly reachable:
```bash
ngrok http 8000
```
Set `PUBLIC_BACKEND_URL` in `.env` to the ngrok URL.

---

## Current active config (`.env`)

```
VOICE_ENABLED=false        # Tier 2/3 agent call not yet triggered by escalation
LYZR_VOICE_AGENT_ID=       # paste from Studio — agent exists but escalation won't call it yet
```

`VOICE_ENABLED=false` means `escalation.py` skips the voice fan-out and only fires Slack.
The agent in Studio is fully configured and can be tested manually. Set `VOICE_ENABLED=true`
once per-call context injection is confirmed working.

---

## Upgrading to Tier 3 (voice)

When voice premium is available in Studio:
1. Enable the **Voice Agent** feature on the `CallSign Voice` agent in Studio.
2. Set **Agent Speaks First: ON**.
3. No backend, tool, or instruction changes needed.

## Upgrading to Tier 4 (real phone call)

Front the same agent with Twilio (outbound dial to `engineer.phone`) and swap in
Deepgram + ElevenLabs. No backend changes — still `resolve_incident` → `/execute`.
