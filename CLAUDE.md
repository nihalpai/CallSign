# CallSign AI

Voice-first AI incident response. When a security alert fires, an AI agent reads the
runbook, scopes the blast radius, and gets a **spoken yes/no** from the on-call
engineer before executing a remediation action — with a live UI that reacts the instant
approval is given.

This file is the **main instruction file**. It holds project-wide rules and points to
focused specs in `docs/`. Read the relevant `docs/` file before working on that area.

---

## Documentation map

| Working on… | Read |
|-------------|------|
| The high-level plan & phases | [Plan.MD](Plan.MD) |
| System design, data flow, SSE, approval-channel abstraction | [docs/architecture.md](docs/architecture.md) |
| **Shared data shapes** (alert, infra state, agent JSON, SSE events) | [docs/data-contracts.md](docs/data-contracts.md) |
| FastAPI endpoints, Python layout | [docs/backend.md](docs/backend.md) |
| The Lyzr Studio brain agents (Diagnostician + Strategist) + prompts | [docs/agents.md](docs/agents.md) |
| **Remediation engine, the simulate⇄real Executor toggle, autonomy policy** | [docs/remediation.md](docs/remediation.md) |
| On-call selection + Slack/voice escalation orchestration | [docs/escalation.md](docs/escalation.md) |
| Slack bot (incident card, the huddle reality) | [docs/slack.md](docs/slack.md) |
| Datadog ingestion + webhook mapping | [docs/datadog.md](docs/datadog.md) |
| Lyzr Studio voice agent, the 3 voice tiers | [docs/voice.md](docs/voice.md) |
| Next.js terminal UI | [docs/frontend.md](docs/frontend.md) |

`docs/data-contracts.md` is the **single source of truth** for any shape that crosses a
boundary. If you change a schema, change it there first, then update consumers.

---

## Golden rules

1. **Proof of concept, not production.** In-memory state, mock alerts, no auth, no DB,
   no Docker. Don't add infrastructure the demo doesn't need.
2. **Lyzr Studio is the one paid platform; everything else is free or future.** All three
   agents — Diagnostician, Strategist (Agent API), and the Voice agent — run on Lyzr Studio
   and your Lyzr credits. The deterministic brain fallback keeps the loop demoable with **no**
   Lyzr calls, so nothing *hard*-depends on it. Deepgram, ElevenLabs, Datadog, Slack, and
   telephony are *future* — each must run disabled-but-logged.
3. **Prove the loop before the polish.** The button-approval loop (Phase 3) must work
   end-to-end before voice is added. Voice is a swappable approval channel, not a
   rewrite — see [docs/architecture.md](docs/architecture.md).
4. **Schemas live in one place.** Cross-boundary data shapes are defined in
   [docs/data-contracts.md](docs/data-contracts.md). Don't redefine them inline.
5. **Nothing is actually exploited or broken in prod.** The UI's "Simulate Alert" POSTs a
   canned payload; in production the same `/webhook/trigger` is hit by Datadog. Keep it
   honest in copy and comments.
6. **Verify before claiming done.** Each milestone has a "Done when" check in
   [Plan.MD](Plan.MD). Run it (curl, browser) — don't assert it works untested.
7. **Simulate by default; real infra is a toggle.** Remediation runs through a
   `RemediationExecutor` interface selected by `EXECUTION_MODE` (`simulate` default).
   Switching to real infra is a config flip + a provider adapter — **never hard-wire a
   provider SDK** into the engine, routes, or brain. Every external integration (Slack,
   voice, Datadog) must run disabled-but-logged so the loop demos with zero accounts.
   See [docs/remediation.md](docs/remediation.md).

---

## Repo layout (target)

```
CallSign/
├── CLAUDE.md                  ← you are here
├── Plan.MD                    ← phased build plan
├── docs/                      ← area specs
├── backend/                   ← FastAPI app (see docs/backend.md)
│   ├── app/                   ← brain/ · remediation/ · escalation.py · integrations/ · routes/
│   ├── runbooks/              ← SOP .md files (security + reliability) — RAG source
│   ├── data/
│   │   ├── infrastructure_state.json
│   │   ├── deployments.json          ← rollback source (§2b)
│   │   ├── on_call.json              ← static on-call schedule (§8)
│   │   └── mock_alerts/{shellshock,bad_deploy,error_spike}.json
│   └── requirements.txt
└── frontend/                  ← Next.js app (see docs/frontend.md)
```

Backend and frontend are independent processes. They communicate over HTTP + SSE only.

---

## Conventions

- **Python:** FastAPI, type hints, Pydantic models for every request/response. Keep the
  Lyzr "brain" callable as a plain function so it can be tested without HTTP.
- **TypeScript/React:** Next.js App Router, Tailwind, function components. No global
  state library — SSE + local state is enough.
- **IDs:** servers/services use stable kebab ids (`auth-01`, `payment-gw`). Reused as keys
  everywhere (state, alerts, UI, agent output).
- **Config & toggles:** all behavior switches live in `app/config.py` from `.env`
  (`EXECUTION_MODE`, `AUTO_REMEDIATE`, `VOICE_ENABLED`, `SLACK_ENABLED`, …). Default to the
  safe/offline value. See the toggle table in [docs/backend.md](docs/backend.md).
- **Commits:** small, per-milestone. Don't commit secrets; keys go in `.env` (gitignored).

## Local run (once built)

```
# backend
cd backend && uvicorn app.main:app --reload          # :8000
# frontend
cd frontend && npm run dev                            # :3000
# voice (Phase 5): expose backend so Lyzr cloud can reach /execute
ngrok http 8000
```
