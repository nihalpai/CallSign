# CallSign AI — Build Roadmap

**A human-in-the-loop approval gate for autonomous AI agents.** An agent about to take a
high-stakes action asks CallSign → CallSign (optionally) enriches it (blast radius, risk, log-based
diagnosis) → routes it to the right human → the human approves over Slack/UI → the action runs (or
the agent runs it) → the dashboard updates live. **A human decides by default; autonomy is opt-in
and off.**

**Incident response is the flagship vertical** (Vertical A below) — one *requester* of the gate,
already built. The pivot work (N1–N6) generalizes that proven pipeline into the public gate.

> Read [CLAUDE.md](CLAUDE.md) first; each area has a focused spec in `docs/`.
> Shapes are defined once in [docs/data-contracts.md](docs/data-contracts.md); the API in
> [docs/approval-api.md](docs/approval-api.md), the client in [docs/sdk.md](docs/sdk.md).

---

## Scope & constraints

- **Proof of concept.** In-memory state, no DB. **Single-tenant** (one shared `APPROVAL_API_KEY`,
  your own Slack); multi-tenant is future. Don't add infra the demo doesn't need.
- **A human decides by default.** Auto-approve is opt-in and OFF; the value is the human checkpoint,
  not autonomy.
- **Simulate by default; real infra is a toggle** (`EXECUTION_MODE`, gate mode only). Every external
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

## Vertical A — Incident response (built): milestones M1–M6

> This whole block is the **flagship vertical**, already built end-to-end in simulate mode. It
> proves the pipeline (enrich → route to a human → act). Under the v3 reframe it's **one requester**
> of the approval gate; the autonomy here is now opt-in/off (see N4). Don't regress it.

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

## The Approval Gate (pivot) — N1–N6

Generalize the proven Vertical-A pipeline into a public gate any external AI agent can call.

### N1 — Generic `/approvals` + ApprovalRequest contract
Add the public front door; the incident pipeline becomes one caller of it.
([approval-api.md](docs/approval-api.md), [data-contracts.md](docs/data-contracts.md) §10–§12)
- **Done when:** an agent can `POST /approvals` with an arbitrary action and it reaches a human on Slack.

### N2 — Wait + execution models
Blocking + async/callback delivery; gate + callback execution. ([remediation.md](docs/remediation.md))
- **Done when:** a blocking caller gets the decision on the open call; a callback caller is POSTed the
  outcome; gate mode runs the action, callback mode hands it back.

### N3 — API key (single-tenant) + Python SDK
Shared `APPROVAL_API_KEY` auth + a thin `approve()` client. ([sdk.md](docs/sdk.md))
- **Done when:** a toy external agent uses `approve()` and blocks on a human's yes/no.

### N4 — Enrichment optional + autonomy OFF by default
Repoint the brain to enrichment (never decides); flip `AUTO_REMEDIATE` default to off.
([agents.md](docs/agents.md), [remediation.md](docs/remediation.md))
- **Done when:** by default every action waits for a human; enrichment can be toggled per request.

### N5 — Generic approvals dashboard UI
War-room → queue of pending requests from any source. ([frontend.md](docs/frontend.md))
- **Done when:** an agent's approval request and an incident both appear in one live queue.

### N6 — Smart triage
Log-based diagnosis (caller sends `diagnostics` → pinpoint from the trace) + expertise routing
(ownership map → owner, fall back to on-call). ([triage.md](docs/triage.md))
- **Done when:** a request carrying logs reaches the *right* expert on Slack with the error
  pre-pinpointed and a suggested action.

**Future:** multi-tenant (signup, per-customer key issuance, per-customer Slack OAuth); voice
channel; routing boosters (deploy metadata, read-only Git/CODEOWNERS, past-incident memory).

---

## Critical path & sequencing

**Vertical A (built):** `M1 → M2 → M3 → M4 → M5 → M6`. M2+M3 are the soul; M4 is the
human-in-the-loop drama; M5 is the "real Datadog alert"; M6 proves the executor toggle.

**Pivot:** `N1 → N2 → N3 → N4 → N5 → N6`. N1–N3 stand up the public gate + SDK (the new product);
N4 makes human-by-default real; N5 gives it a face; N6 is the differentiator (smart triage). De-risk
voice (a future channel) separately — it needs Lyzr premium and is not on this path.

## Testing & verification (E2E)

The whole product is testable **without don-drapor or any cloud account** — it's simulate-first. A
tiny **fake-agent** script drives every path; build a small `harness/` of these alongside N3 (it
doubles as the demo). Full strategy + a feature-coverage table in [docs/testing.md](docs/testing.md).
- **N1–N6 each get a "Done when" curl/script check** plus a pytest case (extend the existing suite).
- don-drapor is needed **only** for the two optional "genuinely real" finales (a real Datadog alert
  source; a real executor rollback) — never to verify a feature works.

## The 90-second demo (target)

**Headline (the gate):**
1. Approvals dashboard on screen. A toy agent decides it wants to **"delete 14,000 stale records"**
   and calls `approve(...)` — it pauses.
2. CallSign enriches (risk: irreversible; blast radius) and **pings you on Slack** with the action
   and an Approve/Deny.
3. You click **Approve**. The decision returns to the agent, which proceeds — and the request flips
   to **APPROVED** on the dashboard live. No autonomy: a human pulled the trigger.

**Secondary (the incident vertical + smart triage):**
4. An agent hits an error and sends **logs**. CallSign pinpoints the failing route/deploy from the
   stack trace, routes it to **the engineer who owns Payments**, suggests a rollback; you approve;
   the service flips to **ROLLED BACK**. Record it.
