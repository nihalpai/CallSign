# CallSign AI

**A human-in-the-loop approval gate for autonomous AI agents.** When an AI agent is about to take
a high-stakes action, it asks CallSign first. CallSign (optionally) enriches the request — scopes
the blast radius, scores the risk, and can pinpoint an error from logs — then routes it to the right
human, who gives a **yes/no** (over Slack today; voice later) before anything runs. **A human decides
every high-stakes action by default; autonomy is opt-in and off.**

**Incident response is the flagship example vertical** built on the gate: a Datadog alert is one
*requester*; the 2-agent brain enriches it; a human approves the remediation. The same pipeline
serves any external agent calling the API.

This file is the **main instruction file**. It holds project-wide rules and points to
focused specs in `docs/`. Read the relevant `docs/` file before working on that area.

---

## Documentation map

| Working on… | Read |
|-------------|------|
| The high-level plan & phases | [Plan.MD](Plan.MD) |
| System design, requester vs approval channels, gate/callback, SSE | [docs/architecture.md](docs/architecture.md) |
| **Shared data shapes** (ApprovalRequest §10, Decision §11, Requester §12) | [docs/data-contracts.md](docs/data-contracts.md) |
| **The approval API** (`POST /approvals`, blocking vs callback) | [docs/approval-api.md](docs/approval-api.md) |
| **The client SDK** (how an external agent hooks up) | [docs/sdk.md](docs/sdk.md) |
| FastAPI endpoints, Python layout | [docs/backend.md](docs/backend.md) |
| Approver routing + expertise routing + Slack notification | [docs/escalation.md](docs/escalation.md) |
| Slack bot (the approval card) | [docs/slack.md](docs/slack.md) |
| Next.js approvals-dashboard UI | [docs/frontend.md](docs/frontend.md) |
| **End-to-end testing** (fake-agent harness, example agent) | [docs/testing.md](docs/testing.md) |
| **Example agent** (GEO agent wired to the gate) | [examples/README.md](examples/README.md) |
| **Wiring snippet** (paste into your real agent) | [examples/WIRING.md](examples/WIRING.md) |

`docs/data-contracts.md` is the **single source of truth** for any shape that crosses a
boundary. If you change a schema, change it there first, then update consumers.

---

## Golden rules

1. **A human decides every high-stakes action.** The product is the *approval gate*, not autonomy.
   Every request waits for a human — there is no auto-approve path. Don't reintroduce autonomy;
   that's the risky, commoditized thing we deliberately stepped away from.
2. **Proof of concept, not production.** In-memory state, mock data, no DB, no Docker.
   **Single-tenant now** (one shared `APPROVAL_API_KEY`, your own Slack). Multi-tenant (signup,
   per-customer key issuance, per-customer Slack OAuth) is **future** — don't build it yet.
3. **Enrichment is optional and never decides.** CallSign may add a risk score and a short
   human-readable summary to a request to help the approver; it never outputs approve/deny. (The
   heavier Lyzr "brain" + log-diagnosis the old incident vertical used was removed in the slim build.)
   Slack is the active notification channel; voice/telephony are *future* and run disabled-but-logged.
4. **Prove the approval loop before the polish.** The agent→ask→human→answer loop (Slack/UI button)
   must work end-to-end before voice or real infra. Voice is a swappable approval channel, not a
   rewrite — see [docs/architecture.md](docs/architecture.md).
5. **Schemas live in one place.** Cross-boundary shapes (ApprovalRequest §10, etc.) are defined in
   [docs/data-contracts.md](docs/data-contracts.md). Don't redefine them inline.
6. **We never read the caller's codebase.** CallSign only sees what an agent sends in the approval
   request (action, context, dangers, estimated cost). No repo access. Keep it honest in copy and comments.
7. **Verify before claiming done.** Each milestone has a "Done when" check in [Plan.MD](Plan.MD).
   Run it (curl, browser) — don't assert it works untested.
8. **Approvals are decision-only.** On a human's yes, CallSign returns the decision and the calling
   agent performs its own action (callback mode). CallSign executing actions itself (gate mode with a
   provider adapter) is *future* — never hard-wire a provider SDK into the routes.

---

## Repo layout (target)

```
CallSign/
├── CLAUDE.md                  ← you are here
├── Plan.MD                    ← phased build plan
├── docs/                      ← area specs
├── backend/                   ← FastAPI app (see docs/backend.md)
│   ├── app/                   ← auth.py · escalation.py · routes/ (approvals.py, …)
│   ├── data/
│   │   └── on_call.json       ← on-call schedule + area ownership (§8)
│   └── requirements.txt
├── sdk/                       ← thin client lib wrapping POST /approvals (see docs/sdk.md) — published separately
├── examples/                  ← runnable example agents (see examples/README.md)
│   ├── geo_agent.py           ← GEO agent wired to the gate
│   ├── WIRING.md              ← copy-paste snippet for your real agent
│   └── output/                ← generated files land here
├── harness/                   ← fake-agent test scripts (see harness/README.md)
└── frontend/                  ← Next.js approvals-dashboard app (see docs/frontend.md)
```

Backend and frontend are independent processes. They communicate over HTTP + SSE only.

---

## Conventions

- **Python:** FastAPI, type hints, Pydantic models for every request/response. Keep enrichment and
  routing as plain functions so they can be tested without HTTP.
- **TypeScript/React:** Next.js App Router, Tailwind, function components. No global
  state library — SSE + local state is enough.
- **IDs:** servers/services use stable kebab ids (`auth-01`, `payment-gw`). Reused as keys
  everywhere (state, alerts, UI, agent output).
- **Config & toggles:** all behavior switches live in `app/config.py` from `.env`
  (`APPROVAL_API_KEY`, `ENRICH_REQUESTS`, `EXPERTISE_ROUTING`, `SLACK_ENABLED`, …). Default to the
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
