# Backend (FastAPI)

> Scope: HTTP/SSE surface, in-memory state, and wiring. AI logic → [agents.md](agents.md);
> remediation → [remediation.md](remediation.md); escalation → [escalation.md](escalation.md);
> shapes → [data-contracts.md](data-contracts.md).

## Responsibilities

The backend is the **approval gate**: take a request, (optionally) enrich it, route it to a human,
deliver the decision. Concretely:

1. Accept **approval requests** (`POST /approvals`, §10) from any caller — and accept **alerts**
   (`/webhook/trigger`, §1b) as one specific requester (the incident vertical).
2. **(Optional) enrich** via the brain (callable function, no HTTP coupling) — blast radius / risk /
   summary, and log-based diagnosis (§13) when `diagnostics` are sent. Enrichment never decides.
3. **Route** to a human approver — expertise routing (area owner, §8) with on-call fallback.
4. Deliver the decision: **gate mode** runs the action via the remediation engine/executor;
   **callback mode** returns the outcome to the caller. Auto-approve is **opt-in, off by default**.
5. Hold infra (§2) + deployments (§2b) + ownership registry (§8) + requests/incidents state in memory.
6. Stream `log` / `state` / `incident` / `approval` over SSE (`/stream`).
7. Accept approval decisions from any channel (`/execute`, the decision sink).

**Data sources it reads** (all caller/operator-provided — **no repo access**): the ownership
registry (`on_call.json`, §8) and caller-supplied `diagnostics` (§13b). See [triage.md](triage.md).

## Project layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, route registration, CORS, startup load
│   ├── config.py               # env, paths, .env, the TOGGLES (see below)
│   ├── models.py               # Pydantic models — mirror data-contracts.md
│   ├── state.py                # infra state (§2): get/set_status/blast_radius
│   ├── deployments.py          # deployments (§2b): current/previous, rollback swap
│   ├── incidents.py            # incident registry (§5) open/update/resolve
│   ├── events.py               # SSE pub/sub (asyncio.Queue fan-out)
│   ├── brain/                  # Lyzr Studio agents (Agent API) — see agents.md
│   │   ├── pipeline.py         # run_brain(alert, log) -> (diagnosis, plan)
│   │   ├── diagnostician.py    # Agent 1: call Studio agent + parse §3
│   │   ├── strategist.py       # Agent 2: call Studio agent + parse §4
│   │   └── fallback.py         # deterministic no-key engine
│   ├── remediation/            # see remediation.md
│   │   ├── engine.py           # policy loop: auto-fix safe, verify, escalate
│   │   ├── executor.py         # RemediationExecutor + SimulatedExecutor
│   │   └── adapters/           # future RealExecutor + provider adapters (stubs)
│   ├── escalation.py           # select_engineer() + escalate()
│   ├── integrations/
│   │   ├── lyzr.py             # call_agent(agent_id, message, session_id) — Studio Agent API
│   │   ├── datadog.py          # map_datadog_payload (only Datadog-aware code)
│   │   └── slack.py            # post_incident / post_thread (no-op when disabled)
│   ├── auth.py                 # X-API-Key check (single shared APPROVAL_API_KEY)
│   └── routes/
│       ├── approvals.py        # POST /approvals, GET /approvals/{id} — the public front door (§10)
│       ├── trigger.py          # POST /webhook/trigger (incident requester → §10)
│       ├── execute.py          # POST /execute (decision sink)
│       ├── stream.py           # GET  /stream  (SSE)
│       ├── incident.py         # GET  /incident/{id}
│       └── slack.py            # POST /slack/interactions (optional)
│
│   (a thin client `sdk/` Python package wraps POST /approvals — published separately; see sdk.md)
├── runbooks/                   # SOP .md files (RAG source) — security + reliability
├── data/
│   ├── infrastructure_state.json
│   ├── deployments.json
│   ├── on_call.json
│   └── mock_alerts/{shellshock,bad_deploy,error_spike}.json
├── requirements.txt
└── .env                        # secrets + toggles (gitignored)
```

## Endpoints

### `POST /approvals` — the public front door  *(new in v3)*
Body: an **ApprovalRequest** (§10). Auth: `X-API-Key`. Full behavior in
[approval-api.md](approval-api.md). Flow: (optional) enrich → route to a human → await decision →
deliver the outcome (§11). Honors `wait` (`blocking` holds the connection; `async` returns
`request_id`) and `mode` (`gate` runs the action via the executor; `callback` returns the decision
for the caller to act). The incident pipeline below is one internal caller of this same flow.

### `GET /approvals/{id}` — poll status  *(new in v3)*
Returns the ApprovalRequest (§10) + status, and the outcome (§11) once decided. For `async` callers
not using a `callback_url`. 404 on unknown id.

### `POST /webhook/trigger`
The **incident-vertical requester**: body is a raw Datadog payload **or** internal `Alert`. Maps it
into an ApprovalRequest (§10), brain-enriched. Flow:
1. `map_datadog_payload()` → `Alert` (§1). Emit `log [SYSTEM] Alert received`.
2. Mark affected service `compromised`/`degraded`; emit `state`. Open incident
   (`status: diagnosing`); emit `incident`.
3. Run the brain → diagnosis (§3) + plan (§4); attach to incident; emit `incident`.
4. **Run the remediation engine** (auto phase): attempt `auto` steps, verify, and either
   resolve **or** escalate — emitting `log`/`state`/`incident` throughout.
5. Return `{ "incident_id": ... }`. Never blocks on human approval.

### `GET /stream` (SSE)
Long-lived `text/event-stream`. On connect, send current `state` immediately. Then forward
every pub/sub event as a **named** SSE event (`log`/`state`/`incident`/`approval`). Use
`sse-starlette`'s `EventSourceResponse`.

### `POST /execute`
Body: §6 (now includes `action` from §4b + `actor`). The single entry point for **every**
channel incl. the auto engine. Flow: resolve/advance the incident, run the action via the
**active executor**, append to `attempts`, mutate state, emit `state`+`incident`+`log`.
Idempotent on already-resolved incidents.

### `GET /incident/{id}`
Returns the full incident (§5) or 404. Used by the UI deep-link and (optionally) the voice
agent to fetch its own context.

### `POST /slack/interactions` (optional)
Signature-verified Slack action handler → `/execute`. Off unless `SLACK_INTERACTIVE=true`.

## Config — the toggles (`config.py`, from `.env`)

| key | code default | demo value | purpose |
|-----|-------------|------------|---------|
| `APPROVAL_API_KEY` | — | set | shared key for `POST /approvals` (`X-API-Key`). Single-tenant; multi-tenant issuance is FUTURE |
| `ENRICH_REQUESTS` | `true` | `true` | run brain enrichment (blast radius/risk/summary, log-diagnosis) on a request. Incident vertical always enriches; raw requests may set `false` |
| `EXPERTISE_ROUTING` | `false` | `true` | route to the **owning expert** (registry §8) with on-call fallback. Off → on-call rule only |
| `EXECUTION_MODE` | `simulate` | `simulate` | `simulate \| real` — selects the executor (gate mode). **The switch to real infra.** |
| `AUTO_REMEDIATE` | `false` | `false` | **opt-in auto-approve** below the severity gate. **OFF by default — a human decides every action.** Turn on only for explicitly-safe, low-risk actions |
| `AUTO_REMEDIATE_MAX_SEVERITY` | `SEV-2` | `SEV-2` | when auto-approve is on, incidents at/above this skip it and escalate immediately |
| `VOICE_ENABLED` | `false` | `false` | triggers Lyzr escalation agent call on escalation — off until per-call context injection confirmed |
| `SLACK_ENABLED` | `false` | `true` | Slack card on escalation — **primary active approval channel** |
| `SLACK_INTERACTIVE` | `false` | `true` | Approve/Deny buttons in the card + `/slack/interactions` route active |
| `SLACK_CALL_MODE` | `off` | `off` | future Slack Calls API (not built) |
| `LYZR_API_KEY` | — | set | Lyzr Studio `x-api-key` for the Agent API (brain). When unset → deterministic fallback |
| `LYZR_API_BASE` | `https://agent-prod.studio.lyzr.ai` | default | Lyzr Agent API base URL |
| `LYZR_DIAGNOSTICIAN_AGENT_ID` | — | set | Studio agent id for Agent 1 (Diagnostician) |
| `LYZR_STRATEGIST_AGENT_ID` | — | set | Studio agent id for Agent 2 (Strategist) |
| `LYZR_VOICE_AGENT_ID` | — | set | Studio escalation agent id — agent configured, call disabled |
| `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | — | set | Slack app credentials |
| `PUBLIC_BACKEND_URL` | — | ngrok URL | Required for Slack interactivity callbacks and Open CallSign deep-links. Update on every ngrok restart. |

Every external integration runs **disabled-but-logged** by default, so the whole flow
demos with zero accounts (executor simulates, Slack logs the card it would post, voice is
off). Missing `LYZR_API_KEY` → deterministic brain + a clear `[SYSTEM]` warning.

## State, events, CORS (unchanged principles)
- Load all `data/*.json` once at startup into module-level objects; mutate in place; every
  mutation emits a `state` event. Single uvicorn worker (asyncio, no locks).
- `events.py`: subscriber `asyncio.Queue` set; `emit_log/emit_state/emit_incident`.
- CORS: allow `:3000` and the ngrok origin for normal requests **and** `/stream`.

## requirements.txt (additions over v1)
```
fastapi
uvicorn[standard]
sse-starlette
pydantic
python-dotenv
httpx                  # also the Lyzr Studio Agent API client (brain) — no SDK needed
slack_sdk              # only used when SLACK_ENABLED
```

> The brain talks to Lyzr **Studio** over plain HTTP (`httpx`); there is **no** `lyzr-automata`
> dependency anymore. All agent behavior is configured in the Studio UI — see [agents.md](agents.md).

## Local checks
- Generic approval (callback mode, blocking): `curl -X POST localhost:8000/approvals -H 'X-API-Key: <key>' -H 'Content-Type: application/json' -d '{"action":"Refund $5,000","context":"dup charge","mode":"callback","wait":"blocking","timeout_sec":120}'` → Slack card logged/posted; the call returns the §11 outcome once you approve.
- Trigger the incident vertical: `curl -X POST localhost:8000/webhook/trigger -d @data/mock_alerts/bad_deploy.json -H 'Content-Type: application/json'` → `/stream` shows diagnose → route to a human (auto-approve off) → approve → resolve.
- Decide via the sink: `curl -X POST localhost:8000/execute -d '{...approve...}'` → state flips, request `resolved`.
