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
| The Lyzr Automata 2-agent brain + prompts | [docs/agents.md](docs/agents.md) |
| Lyzr Studio voice agent, the 3 voice tiers | [docs/voice.md](docs/voice.md) |
| Next.js terminal UI | [docs/frontend.md](docs/frontend.md) |

`docs/data-contracts.md` is the **single source of truth** for any shape that crosses a
boundary. If you change a schema, change it there first, then update consumers.

---

## Golden rules

1. **Proof of concept, not production.** In-memory state, mock alerts, no auth, no DB,
   no Docker. Don't add infrastructure the demo doesn't need.
2. **Free tools first.** Only Lyzr Studio is paid-for/available today. Deepgram,
   ElevenLabs, and telephony are *future* — nothing may hard-depend on them.
3. **Prove the loop before the polish.** The button-approval loop (Phase 3) must work
   end-to-end before voice is added. Voice is a swappable approval channel, not a
   rewrite — see [docs/architecture.md](docs/architecture.md).
4. **Schemas live in one place.** Cross-boundary data shapes are defined in
   [docs/data-contracts.md](docs/data-contracts.md). Don't redefine them inline.
5. **Nothing is actually exploited.** "Trigger Exploit" POSTs a canned payload. This is
   a scripted demo; keep it honest in copy and comments.
6. **Verify before claiming done.** Each phase has a "Done when" check in
   [Plan.MD](Plan.MD). Run it (curl, browser) — don't assert it works untested.

---

## Repo layout (target)

```
CallSign/
├── CLAUDE.md                  ← you are here
├── Plan.MD                    ← phased build plan
├── docs/                      ← area specs
├── backend/                   ← FastAPI app (see docs/backend.md)
│   ├── app/
│   ├── runbooks/              ← 3 fake SOP .md files (RAG source)
│   ├── data/
│   │   ├── infrastructure_state.json
│   │   └── mock_alerts/shellshock.json
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
- **IDs:** servers use stable kebab ids (`auth-01`, `payment-gw`). Reused as keys
  everywhere (state, alerts, UI, agent output).
- **Commits:** small, per-phase. Don't commit secrets; keys go in `.env` (gitignored).

## Local run (once built)

```
# backend
cd backend && uvicorn app.main:app --reload          # :8000
# frontend
cd frontend && npm run dev                            # :3000
# voice (Phase 5): expose backend so Lyzr cloud can reach /execute
ngrok http 8000
```
