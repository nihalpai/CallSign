# CallSign AI — Build Roadmap

**Voice-first, auto-remediating incident response.** A real production incident is caught by
Datadog → CallSign diagnoses it and pinpoints the exact location → it auto-attempts the safe
fixes → if that's not enough it pages the on-call engineer over Slack **and** a phone call →
the engineer approves (voice or UI) → CallSign remediates → the war-room UI updates live.

> Read [CLAUDE.md](CLAUDE.md) first; each area has a focused spec in `docs/`.
> Shapes are defined once in [docs/data-contracts.md](docs/data-contracts.md).

---

## Scope & constraints

- **Proof of concept.** In-memory state, no auth, no DB. Don't add infra the demo doesn't need.
- **Simulate by default; real infra is a toggle** (`EXECUTION_MODE`). Every external
  integration runs disabled-but-logged so the loop demos with zero accounts.
- **Free tools first.** Lyzr Studio is available now. Datadog (Pro trial), Slack, telephony,
  Deepgram/ElevenLabs are *future* — nothing hard-depends on them.
- **Prove the loop before the polish**, then layer autonomy → escalation → real source.

---

## ✅ Iteration 1 — the loop (COMPLETE)

The button-approval loop, proven end-to-end and tested (37 backend + 6 frontend tests green):

- World: runbooks, `infrastructure_state.json`, mock Shellshock alert.
- Brain: 2-agent pipeline with a deterministic no-key fallback.
- Backend: `/webhook/trigger`, `/execute`, `/stream` (SSE), `/incident/{id}`; in-memory state.
- Frontend: two-panel SOC war-room; trigger → live logs → approve → tile flips.

This is the foundation everything below extends. **Don't regress it** — the tests guard it.

---

## Milestones (v2)

### M1 — Multi-scenario UI
Make all incident types demoable from the UI (answers "how do I trigger the other issues").
- Add mock alerts (`bad_deploy.json`, `error_spike.json`) alongside `shellshock.json`.
- Replace the single "Trigger Exploit" with a **Simulate Alert** scenario picker
  ([docs/frontend.md](docs/frontend.md)).
- The brain already routes by content — verify each scenario hits the right runbook/plan.
- **Done when:** the picker fires isolate / rollback / restart paths, each visible in the UI.

### M2 — Lyzr Studio brain agents (Diagnostician + Strategist)
Provision both agents in **Lyzr Studio** (model, prompt, runbook KB configured in the UI) and
call them from the backend over the **Agent API** (`httpx`, `app/integrations/lyzr.py`). Drop
the `lyzr-automata` dependency. Generalize to reliability incidents.
- Agent 1 **Diagnostician** → diagnosis (§3) incl. `incident_type` + `exact_location`.
- Agent 2 **Strategist** → ordered remediation plan (§4) with `auto`/`human` tags + script.
- Config: `LYZR_API_KEY` + `LYZR_DIAGNOSTICIAN_AGENT_ID` + `LYZR_STRATEGIST_AGENT_ID`.
- Keep the deterministic fallback as the no-key safety net. ([docs/agents.md](docs/agents.md))
- **Done when:** the Studio agents' output matches the §3/§4 contracts; tests still green.

**Studio configuration status (complete):**
- Diagnostician: configured with gpt-4o, concise Role + Goal, full Instructions (input format,
  classification rules, output rules), all 5 runbooks uploaded as `.txt` to a Classic KB
  (RAG, Basic retrieval, 6 chunks, score threshold 0.3), Structured Output JSON schema
  (`name: "diagnosis"`, `strict: true`) enforcing the §3 contract. No tools or memory.
- Strategist: configured with gpt-4o, concise Role + Goal, full Instructions (autonomy rules,
  script rules, output rules), Structured Output JSON schema (`name: "remediation_plan"`,
  `strict: true`) enforcing the §4 contract. No KB, no tools, no memory.
- Both agents in the same Studio account; backend authenticates with one `LYZR_API_KEY`.
- **Remaining:** populate `.env` with real agent IDs → run end-to-end test.

### M3 — Remediation engine + autonomy (simulate executor)
The "auto-fix safe, escalate rest" core. ([docs/remediation.md](docs/remediation.md))
- `RemediationExecutor` interface + `SimulatedExecutor`; `EXECUTION_MODE` toggle.
- `deployments.json` (§2b) so `rollback_deployment` has something to revert.
- Engine: walk plan steps, run `auto` ones, **verify**, resolve or escalate; severity gate.
- **Done when:** a `bad_deploy` alert auto-rolls-back and resolves; a scripted "rollback
  fails" path proceeds to escalation. All simulated.

### M4 — Escalation (on-call + Slack + voice)
Reach a human when auto-remediation isn't enough.
([docs/escalation.md](docs/escalation.md), [docs/slack.md](docs/slack.md), [docs/voice.md](docs/voice.md))
- `on_call.json` (§8) + `select_engineer()` (timezone/shift/status).
- Slack bot posts the incident card (§9) with exact location, the Strategist's spoken script,
  and interactive Approve/Deny buttons → `/slack/interactions` → `/execute`.
- Lyzr escalation agent (text now, voice later) configured in Studio with `resolve_incident`
  custom OpenAPI tool → `/execute`. `VOICE_ENABLED=false` until per-call context injection
  is confirmed with Lyzr Studio (the open risk — see [docs/voice.md](docs/voice.md)).
- **Done when:** an escalated incident pages a selected engineer; approving (UI or Slack button)
  resolves it; the UI shows who was paged.

**Configuration status (complete):**
- Slack app provisioned: `chat:write`, `chat:write.public`, `im:write` scopes. Interactivity
  enabled, Request URL set to `{PUBLIC_BACKEND_URL}/slack/interactions`. `SLACK_ENABLED=true`,
  `SLACK_INTERACTIVE=true`. Card includes `plan.script` as the 📞 block.
- Escalation agent (`CallSign Voice`) configured in Studio as a text agent: concise Role +
  Goal, full Instructions (script delivery, decision capture, out-of-scope fallback), custom
  OpenAPI tool `callsign_resolve_incident` POSTing to `/execute` with `actor: "voice"` as a
  default body parameter. `VOICE_ENABLED=false` — agent exists but escalation won't call it
  until per-call context injection is confirmed.
- **Remaining:** populate `.env` with `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`,
  `PUBLIC_BACKEND_URL`, `LYZR_VOICE_AGENT_ID` → run end-to-end test.

### M5 — Datadog ingestion
Make the alert real. ([docs/datadog.md](docs/datadog.md))
- `map_datadog_payload()` (§1b) — the only Datadog-aware code.
- Build/test with a Datadog-shaped `curl` first (no account needed); then point a real
  monitor + webhook (Pro trial) at the ngrok URL from the Don Draper project.
- **Done when:** a real Datadog monitor firing drives the full loop end-to-end.

### M6 — One real executor adapter (optional showcase)
Make a single action genuinely affect infra, behind `EXECUTION_MODE=real`.
- Implement one `RealExecutor` provider adapter (e.g. Vercel rollback) for one action.
- **Done when:** with the toggle flipped, one approved action performs a real, reversible
  change; flipping back returns to full simulation. No other code changes required.

---

## Critical path & sequencing

`M1 → M2 → M3 → M4 → M5 → M6`. M2+M3 are the soul (real AI + autonomy); M4 is the
human-in-the-loop drama; M5 is the headline ("real Datadog alert"); M6 proves the toggle is
real. De-risk **M4's Lyzr per-call context injection** with a short Studio spike before
building it.

## The 90-second demo (target)
1. War-room UI on screen. Induce a fault in Don Draper (or click Simulate Alert).
2. Watch CallSign diagnose, pinpoint the exact route/deploy, and **auto-attempt a rollback**.
3. It "fails" verification → **Slack pings + your phone rings**; the voice reads the tailored
   script; you say "yes."
4. The affected service flips to **RECOVERED / ROLLED BACK** instantly. Record it.
