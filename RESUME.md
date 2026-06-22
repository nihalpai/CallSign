# RESUME — session handoff

> Drop-in context for a fresh Claude Code session (started after moving this repo to a
> local, non-iCloud folder). Read [CLAUDE.md](CLAUDE.md) for project rules, then this.
> Last updated: 2026-06-17.

## TL;DR
CallSign **v2 (incident response) is built, working, and merged to `main`** (simulate mode, with
the user's real Lyzr agents). 171 backend tests + frontend tests pass.

**New direction (decided, docs written):** reframe CallSign into a **human-in-the-loop approval
gate** any external AI agent can call (Slack/UI approval; voice deferred — no Lyzr premium yet).
v2 incident response becomes the flagship *vertical*. The `docs/` are fully updated; next is
**coding N1–N6** (see [Plan.MD](Plan.MD) "The Approval Gate (pivot)"). No code written for the
pivot yet.

## ⚠️ Why this repo was moved (don't re-diagnose)
The repo was living in `~/Documents` which is **synced to iCloud**. iCloud's sync daemon
thrashing on `node_modules` / `.venv` / `.git` caused intermittent IO failures the whole
session: 100s-slow imports, transient `ModuleNotFoundError`, half-written files, and
`git`/`cp`/`rsync` failing with `Operation timed out` / `Stale NFS file handle`. The fix was
to move the project to a local non-synced folder (e.g. `~/Developer`). **If you see weird
slow/flaky IO again, the project is back on a synced/network path — that's the cause, not the code.**

## ▶️ First action
The v2 build is **already merged to `main`** (the earlier "push the commit" task is done —
`main` == `origin/main`). If deps aren't built yet:
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ../frontend && npm install
```
Then start coding the pivot (N1 first: `POST /approvals` + the ApprovalRequest contract).
Remote: `https://github.com/nihalpai/CallSign.git`.

> Minor housekeeping (non-blocking): a stray broken git ref `.git/refs/heads/main 2` (an iCloud
> dup-name artifact) makes `git branch -a` warn — safe to `rm ".git/refs/heads/main 2"`.

## How to run it (simulate mode, works today)
```bash
# backend — MUST be app.main:app, run from backend/, no --reload
cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000
# frontend (separate terminal) — ONE npm process at a time
cd frontend && npm run dev      # http://localhost:3000
```
- First cold start can take ~30s (framework imports); wait for `Application startup complete`.
- `address already in use` → `lsof -ti tcp:8000 | xargs kill`.

## Config state (user has configured these)
- **Lyzr brain is LIVE.** `backend/.env` has real `LYZR_API_KEY` + `LYZR_DIAGNOSTICIAN_AGENT_ID`
  + `LYZR_STRATEGIST_AGENT_ID`. The two Studio agents (Diagnostician, Strategist) respond and
  return valid §3/§4 JSON. (`.env` is gitignored — never commit it.)
- **Slack enabled** (`SLACK_ENABLED=true`, `SLACK_INTERACTIVE=true`); `slack_sdk` installed.
  Needs `PUBLIC_BACKEND_URL` (ngrok) for the Open-CallSign deep-link + interactivity. **The
  ngrok URL changes every restart — update `.env` AND the Slack app's Interactivity URL each time.**
- `EXECUTION_MODE=simulate` (nothing real is touched). `VOICE_ENABLED=false`.

## Fixes applied this session (already committed)
- **Lazy `httpx` import** in `app/integrations/lyzr.py` — keeps ~40s off cold startup.
- **Hermetic tests** — `tests/conftest.py` forces fallback + disabled integrations so the
  suite never uses the real `.env` creds (was secretly calling live Lyzr/Slack).
- **Unique per-incident Lyzr `session_id`** (was reusing a constant → one ever-growing Studio
  conversation; that's why the user saw "~100 calls, no order"). Now `session_id = incident_id`.
- **`slack_sdk`** added/installed (was `ModuleNotFoundError` on escalation).

## What works (verified live in the browser)
> Note: the pivot (N4) flips `AUTO_REMEDIATE` default **off** — a human decides by default. The
> autonomy path below stays in the code as **opt-in**, not the default behavior.
- **Autonomy path (opt-in):** a `bad_deploy`/`error_spike` alert → auto-remediation (rollback/restart)
  → resolved, no human. (With the real Diagnostician, a SEV-1 bad_deploy escalates instead —
  correct: SEV-1 is above the `AUTO_REMEDIATE_MAX_SEVERITY=SEV-2` gate.)
- **Escalation path:** SEV-1/security → escalate → on-call engineer selected → Slack card +
  voice "would call" logged → Approve in UI → action runs (simulated) → resolved.
- Logs: `backend/logs/callsign.log` (rotating) has the full structured trace.

## Next direction — the approval-gate pivot (N1–N6)
Generalize the proven incident pipeline into a public gate any external AI agent can call. The
docs are written; build in order ([Plan.MD](Plan.MD) "The Approval Gate (pivot)"):
1. **N1** — `POST /approvals` + the ApprovalRequest contract (§10); incident pipeline becomes one caller.
2. **N2** — blocking + callback wait; gate + callback execution.
3. **N3** — single-tenant `APPROVAL_API_KEY` + a thin Python `approve()` SDK.
4. **N4** — brain → optional enrichment; flip `AUTO_REMEDIATE` default OFF (human decides by default).
5. **N5** — war-room → generic approvals-dashboard UI.
6. **N6** — smart triage: log-based diagnosis (caller sends logs) + expertise routing (area owner).

Key shapes/endpoints live in [docs/data-contracts.md](docs/data-contracts.md) (§10–§14),
[docs/approval-api.md](docs/approval-api.md), [docs/sdk.md](docs/sdk.md), [docs/triage.md](docs/triage.md).
The earlier "wire don-drapor → real rollback" idea is now folded into N6 + the *future* real-executor
work (gate mode), not the next step.

## Doc map
[Plan.MD](Plan.MD) roadmap · [docs/architecture.md](docs/architecture.md) · [docs/data-contracts.md](docs/data-contracts.md)
(single source of truth for shapes) · [docs/approval-api.md](docs/approval-api.md) (the gate API) ·
[docs/sdk.md](docs/sdk.md) (how agents hook up) · [docs/triage.md](docs/triage.md) (log-diagnosis + routing) ·
[docs/agents.md](docs/agents.md) (Lyzr agents — optional enrichment) · [docs/remediation.md](docs/remediation.md) ·
[docs/escalation.md](docs/escalation.md) · [docs/slack.md](docs/slack.md) · [docs/datadog.md](docs/datadog.md) ·
[docs/voice.md](docs/voice.md) · [docs/frontend.md](docs/frontend.md) · [docs/backend.md](docs/backend.md) ·
[docs/testing.md](docs/testing.md) (E2E without the real project) · [SETUP.md](SETUP.md) (external keys).
