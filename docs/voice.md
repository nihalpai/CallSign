# Voice (Lyzr Studio)

> Scope: turning the Commander script into a spoken approval conversation. Voice is a
> **swappable approval channel** (see [architecture.md](architecture.md)); it is added
> *after* the button-approval loop works. The brain/state/UI don't change when voice is
> wired in.

## The three tiers

| Tier | Channel | Needs | Status |
|------|---------|-------|--------|
| **0** | UI button → POST `/execute` | nothing | build first (Phase 3) |
| **1** | Lyzr Studio voice agent, browser mic/speaker → tool → `/execute` | Lyzr Studio (have it) | Phase 5 |
| **2** | Real outbound phone call | Twilio + Deepgram/ElevenLabs | future, optional |

All tiers converge on the **same** `POST /execute` (data-contracts §6). That is the whole
point — nothing downstream knows which tier fired.

## Tier 1 — Lyzr Studio voice agent (the target for the demo)

### Configuration
- **Behavior:** *Agent Speaks First* — it opens with the script, doesn't wait for the
  human to talk.
- **Latency:** select Lyzr's lowest-latency / realtime engine. Emergency tool → snappy
  turn-taking matters more than perfect prosody.
- **STT/TTS:** use whatever Lyzr Studio provides out of the box for the PoC. Deepgram /
  ElevenLabs keys are a *future* quality upgrade, not a dependency.

### The custom tool: `isolate_container`
Define a tool in Lyzr Studio that fires when the human approves. It performs:
```
POST {PUBLIC_BACKEND_URL}/execute
{ "incident_id": "...", "decision": "approve", "action": "isolate_container", "target": "auth-01" }
```
- The tool needs the live `incident_id`, `action`, `target`. These come from how the
  script is injected (below).
- Also define the deny path (decision `deny`) or let the agent end the call without
  calling the tool (then a timeout/explicit deny resolves the incident).

### Getting the per-incident script into the voice agent — OPEN RISK
The dynamic-script idea depends on Lyzr letting us set per-call context at trigger time.
**Confirm which of these Lyzr Studio supports before building Phase 5:**
1. **Per-call system-prompt / context injection** at session start (ideal: pass the
   Commander `script`, `incident_id`, `action`, `target`).
2. **Input variables / metadata** passed into the session that the agent and tool can read.
3. If neither: the agent fetches its own context — backend exposes
   `GET /incident/{id}` and the voice agent's opening step calls it.

Pick the first one Lyzr actually supports. This is the single biggest integration unknown
— resolve it early.

### Reachability — backend must be public
Lyzr's cloud calls the tool, so it can't reach `localhost`. Expose the local backend:
```
ngrok http 8000      # free tier; use the https URL as PUBLIC_BACKEND_URL
```
Update the tool URL and CORS (backend.md) with the ngrok origin.

### Voice-agent guardrails (Phase 6)
- **Fallback line:** if asked something out of scope →
  *"I do not have that context. Escalating to tier 2."* Configure as the agent's
  unknown-question behavior; do not let it improvise security advice.
- Keep it on-script: its only job is to read the script and capture a yes/no.

## Tier 2 — real phone call (future)
When telephony is in budget: front the same Lyzr voice agent with Twilio (outbound dial
to your cell), and swap Lyzr's built-in STT/TTS for Deepgram + ElevenLabs for quality.
**No backend changes** — still the same `isolate_container` → `/execute`. This is the
"hold the phone to the mic" moment from the demo script (Plan.MD Phase 7).

## Demo note
Tier 1 already *sounds* like the phone demo (a voice reads the script, you say "yes,
isolate it," the UI flips). Record with Tier 1 if Tier 2 isn't ready — it loses little.
