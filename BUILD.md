# CallSign — Build Summary (the Approval Gate)

> What was built, how it's architected, and exactly what you need to do to run it, test it, and
> see the flow. For the design rationale and per-area specs, see [CLAUDE.md](CLAUDE.md) and `docs/`.

---

## 1. What this is

**CallSign is a human-in-the-loop approval gate for autonomous AI agents.** When an agent is about
to take a high-stakes action (refund money, delete records, roll back a deploy), it asks CallSign
first. CallSign optionally **enriches** the request — scores risk, scopes blast radius, and can
**pinpoint an error from logs the caller sends** — then **routes** it to the right human, who gives a
**yes/no** over Slack or the dashboard before anything runs.

- **A human decides every high-stakes action by default.** Autonomy (auto-approve) is opt-in and OFF.
- **The app never reads your codebase.** Log-based diagnosis works only on logs the caller *sends*.
- **Incident response is one vertical** (a Datadog alert is one "requester") built on the same gate.
- **Single-tenant PoC:** one shared API key, your own Slack, in-memory state. Multi-tenant + voice
  are documented as future.

---

## 2. Architecture

Two distinct abstractions:

- **Requester channel** = *who asks.* An external agent (`POST /approvals`), or the incident
  pipeline (`/webhook/trigger`, fed by Datadog).
- **Approval channel** = *who answers.* The dashboard button, Slack card, or (future) voice.

```
REQUESTERS                         CALLSIGN (the gate)                     APPROVAL CHANNELS
──────────                         ───────────────────                     ─────────────────
External AI agent ─POST /approvals─┐
                                   ├─► 1. (optional) ENRICH                 Dashboard button ─┐
Incident pipeline ─/webhook/trigger┤      risk · blast radius               Slack card        ─┤
  (Datadog → Alert → request)      │      log-based diagnosis (from logs)    voice (future)    ─┤
                                   │   2. ROUTE to a human                          │
                                   │      expertise routing → area owner            │ approve/deny
                                   │      (fallback: on-call)                        ▼
                                   │   3. capture DECISION  ◄───────────────  POST /execute
                                   └─► 4. DELIVER OUTCOME:
                                         • gate mode    → run action via executor (simulate|real)
                                         • callback mode→ return decision; the agent acts
                                         • blocking → return on the open call · async → callback/poll

   log / state / incident / approval events stream to the Next.js dashboard over SSE the whole time.
```

The whole system is **simulate-first**: every external integration (executor, Slack, voice, Datadog,
Lyzr brain) runs disabled-but-logged or simulated, so the full flow works with **zero accounts**.

---

## 3. What was built (file map)

### Backend — `backend/app/` (FastAPI, in-memory)
| File | Role |
|------|------|
| `routes/approvals.py` | **NEW** — `POST /approvals`, `GET /approvals/{id}`: create → enrich → route → wait → deliver |
| `requests.py` | **NEW** — in-memory ApprovalRequest store + blocking-wait registry (`asyncio.Event` per request) |
| `auth.py` | **NEW** — `X-API-Key` dependency (open when `APPROVAL_API_KEY` unset; 401 on mismatch) |
| `enrichment.py` | **NEW** — `enrich_request()`: risk + blast radius + log-diagnosis; best-effort, never decides |
| `brain/logs.py` | **NEW** — `diagnose_from_logs()`: parses a stack trace (Python/JS) to file/function/line; Lyzr or deterministic; **no codebase access** |
| `routes/execute.py` | **EXTENDED** — `apr-*` ids resolve approval requests (gate-run or callback-return, fire waiter, best-effort callback POST); incident ids unchanged |
| `escalation.py` | **EXTENDED** — `select_approver(area)`: expertise routing to the area owner, graceful fallback to on-call |
| `config.py` | **EXTENDED** — `APPROVAL_API_KEY`, `ENRICH_REQUESTS` (default on), `EXPERTISE_ROUTING` (default off); `AUTO_REMEDIATE` default flipped **off** |
| `models.py` | **EXTENDED** — `ApprovalCreate`, `ApprovalRequest`, `DecisionOutcome`, `RequesterIdentity`, `DiagnosticsInput`, `DiagnosisFromLogs` |
| `events.py` | **EXTENDED** — `emit_approval()` → SSE `approval` event |
| `data/on_call.json` | **EXTENDED** — engineers gained `owns` areas (for expertise routing) |
| *(unchanged v2)* | `brain/` pipeline, `remediation/` engine+executor, `integrations/`, `state.py`, `incidents.py`, `routes/{trigger,stream,incident,slack}.py` |

### SDK — `sdk/` (published-separately Python client)
- `callsign/client.py` — `CallSignClient`, `approve()` (blocking), `approve_async()`, `get_request()`, `Decision`, `CallSignError`.
- `pyproject.toml`, `README.md`, `tests/test_client.py` (httpx `MockTransport`, no live backend needed).

### Frontend — `frontend/` (Next.js dashboard)
- `components/ApprovalsQueue.tsx` — live queue of pending requests (risk badge, status, routed-to).
- `components/ApprovalDetail.tsx` — selected request: action, context, blast radius, Approve/Deny → `POST /execute`.
- `components/TriagePanel.tsx` — diagnosed location + probable cause + suggested action + routed-to.
- `app/page.tsx` — adds the `approval` SSE listener; keeps the incident war-room intact.
- `lib/types.ts` — `ApprovalRequest`, `DiagnosisFromLogs`, `DecisionOutcome`.

### Harness — `harness/` (fake-agent E2E drivers / demo)
- `refund_bot.py` — plain gate, callback mode, blocking.
- `delete_bot.py` — async + a local callback listener.
- `error_with_logs_bot.py` — gate mode + diagnostics (the **smart-triage headline**).
- `trigger_incident.sh` — curls a mock Datadog alert at `/webhook/trigger` (the incident vertical).
- `README.md` — env vars + a numbered full E2E pass.

---

## 4. The API

| Method · Path | Purpose |
|---|---|
| `POST /approvals` | create an approval request (auth: `X-API-Key`). `wait`=blocking\|async, `mode`=gate\|callback. Blocking returns the `DecisionOutcome`; async returns `{request_id, status}` |
| `GET /approvals/{id}` | poll a request's status + outcome |
| `POST /execute` | the decision sink — resolves both incidents and `apr-*` requests |
| `GET /stream` | SSE: `log` / `state` / `incident` / `approval` events |
| `POST /webhook/trigger` | the incident-vertical requester (Datadog or internal Alert) |
| `GET /incident/{id}` | the incident-vertical view |

**ApprovalRequest** (`POST /approvals` body): `action` (required), `target`, `context`,
`diagnostics{logs,stack_trace,deploys}`, `risk`, `mode`, `callback_url`, `wait`, `timeout_sec`,
`approvers`. **DecisionOutcome**: `{request_id, approved, decision(approve|deny|timeout), actor, decided_at, detail}`.

Full shapes: [docs/data-contracts.md](docs/data-contracts.md) §10–§14. API detail: [docs/approval-api.md](docs/approval-api.md).

---

## 5. Config toggles (`backend/.env`)

| Key | Default | Effect |
|---|---|---|
| `APPROVAL_API_KEY` | unset | shared key for `/approvals`. Unset → auth OPEN (logs a warning) |
| `ENRICH_REQUESTS` | `true` | run brain enrichment (risk/blast radius/log-diagnosis) on a request |
| `EXPERTISE_ROUTING` | `false` | route to the area owner (else on-call) |
| `AUTO_REMEDIATE` | **`false`** | opt-in auto-approve. **Off = a human decides every action** |
| `EXECUTION_MODE` | `simulate` | `simulate \| real` (gate-mode executor) |
| `LYZR_API_KEY` (+ agent ids) | unset | real brain enrichment; unset → deterministic fallback |
| `SLACK_ENABLED` / `SLACK_INTERACTIVE` | `false` | Slack approval card + buttons; off → logged |

---

## 6. Test coverage

| Suite | Result | What it guards |
|---|---|---|
| Backend `pytest` | **217 passed** | gate (blocking/async, gate/callback, auth, timeout), log-diagnosis parsing, expertise routing + fallback, enrichment, plus all v2 incident behavior |
| SDK `pytest` | **19 passed** | request body/headers, blocking Decision, async, 401, diagnostics passthrough (httpx MockTransport) |
| Frontend `vitest` | **61 passed** | ApprovalsQueue / ApprovalDetail / TriagePanel render + Approve POST, plus existing components |

Run them: `cd backend && .venv/bin/pytest -q` · `sdk/.venv/bin/python -m pytest sdk/tests -q` ·
`cd frontend && npm test`.

> Known pre-existing nit (not from this build): `npx tsc --noEmit` flags vitest globals in
> `app/layout.test.tsx` (a test file from the v2 commit). Harmless — `next build` excludes test files.

---

## 7. RUN IT — your step-by-step

### A. Run it locally (nothing external required)

1. **Backend** (terminal 1):
   ```bash
   cd backend
   APPROVAL_API_KEY=demo-key-123 EXPERTISE_ROUTING=true .venv/bin/uvicorn app.main:app --port 8000
   ```
   Wait for `Application startup complete`. (Cold start can take ~30s.) Auth is on with that key;
   omit `APPROVAL_API_KEY` to run with open auth.
2. **Frontend** (terminal 2):
   ```bash
   cd frontend && npm run dev      # http://localhost:3000
   ```
3. Open **http://localhost:3000** — the approvals dashboard.

### B. The GEO agent flow (the headline demo)

This shows a real AI agent — the GEO agent that generates `LLMs.txt` via Lyzr Studio — gated
behind a human approval.

1. **Run the GEO agent example** (terminal 3):
   ```bash
   export APPROVAL_API_KEY=demo-key-123
   export CALLSIGN_BASE_URL=http://localhost:8000
   python examples/geo_agent.py
   ```
   The script blocks with "Requesting approval from CallSign …".

2. **Approve** in the dashboard (http://localhost:3000) — find the "Generate LLMs.txt (GEO agent)"
   request, review the `dangers` list and `estimated_tokens`, click **Approve**.

   Or approve via curl:
   ```bash
   # Find the request_id
   curl -s http://localhost:8000/approvals -H "X-API-Key: $APPROVAL_API_KEY" | python3 -m json.tool
   # Approve
   curl -s -X POST http://localhost:8000/execute \
     -H "Content-Type: application/json" -H "X-API-Key: $APPROVAL_API_KEY" \
     -d '{"request_id":"<id>","decision":"approve","actor":"you"}'
   ```

3. **The agent unblocks** and prints "approved — generated LLMs.txt (would have spent credits)".
   The file appears at `examples/output/LLMs.txt`. On deny it prints "denied — skipped generation".

**With real Slack approvals** (`SLACK_ENABLED=true`):
- Set `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, and your `slack_id` in `data/on_call.json`.
- Expose the backend: `ngrok http 8000` (required for Slack interactivity buttons).
- The approval card arrives in your Slack DM. Clicking Approve/Deny there resolves the request.
- The dashboard Approve button works without ngrok.

**Other harness scripts** (plain gate, async callback):
- `python harness/refund_bot.py` — callback mode, blocking.
- `python harness/delete_bot.py` — async + local callback listener.
- `bash harness/trigger_incident.sh` — the incident vertical (mock Datadog alert).

### C. Run the tests

```bash
cd backend && .venv/bin/pytest -q          # 217
sdk/.venv/bin/python -m pytest sdk/tests -q # 19
cd frontend && npm test                     # 61
```

### D. What needs EXTERNAL setup (all optional — see [SETUP.md](SETUP.md))

Everything above works with **no external accounts**. You only need external setup to upgrade
specific capabilities:

| To enable… | Do this |
|---|---|
| **Real AI enrichment** (instead of the deterministic brain) | Lyzr Studio: create the Diagnostician + Strategist agents, put `LYZR_API_KEY` + agent ids in `backend/.env` (uses your Lyzr credits) |
| **Real Slack approvals** (a card in a real workspace) | Create a Slack app, set `SLACK_BOT_TOKEN` + `SLACK_SIGNING_SECRET`, `SLACK_ENABLED=true`, put your `slack_id`s in `data/on_call.json`; expose the backend via `ngrok` for interactivity |
| **Real Datadog alerts** as the source | Datadog Pro trial → monitor → webhook to `{PUBLIC_BACKEND_URL}/webhook/trigger` (template in §1b). Only needed for the "real alert" showcase — a curl proves the same path |
| **Real executor** (a genuinely real rollback) | Implement one provider adapter under `app/remediation/adapters/` and set `EXECUTION_MODE=real` + provider creds. The one thing that touches real infra |
| **Voice approval channel** | Deferred — needs Lyzr premium. The agent is configured; `VOICE_ENABLED=false` |
| **Multi-tenant** (other customers sign up) | Future — per-customer signup, key issuance, and per-customer Slack OAuth. Not built |

### E. Internal config you control (no external accounts)

- **`backend/data/on_call.json`** — your approvers and the `owns` areas that drive expertise routing.
- **`backend/data/infrastructure_state.json`** / **`deployments.json`** — the simulated services/deploys.
- **Toggles** in `backend/.env` (table in §5) — most importantly `APPROVAL_API_KEY`,
  `EXPERTISE_ROUTING`, and keeping `AUTO_REMEDIATE=false` (human decides by default).

---

## 8. Where to read more

[CLAUDE.md](CLAUDE.md) (rules + map) · [Plan.MD](Plan.MD) (roadmap, N1–N6) ·
[docs/architecture.md](docs/architecture.md) · [docs/approval-api.md](docs/approval-api.md) ·
[docs/sdk.md](docs/sdk.md) · [docs/triage.md](docs/triage.md) ·
[docs/data-contracts.md](docs/data-contracts.md) · [docs/testing.md](docs/testing.md) ·
[SETUP.md](SETUP.md) (external keys).
