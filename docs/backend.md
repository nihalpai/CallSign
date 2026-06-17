# Backend (FastAPI)

> Scope: HTTP/SSE surface, in-memory state, and wiring. AI logic → [agents.md](agents.md);
> remediation → [remediation.md](remediation.md); escalation → [escalation.md](escalation.md);
> shapes → [data-contracts.md](data-contracts.md).

## Responsibilities

1. Accept alerts (`/webhook/trigger`) — map a Datadog payload → internal `Alert` (§1b).
2. Run the brain (callable function, no HTTP coupling).
3. Run the **remediation engine** (auto-fix safe steps, verify) and **escalate** when needed.
4. Hold infra (§2) + deployments (§2b) + on-call (§8) state in memory and mutate it.
5. Stream `log` / `state` / `incident` over SSE (`/stream`).
6. Accept approval decisions from any channel (`/execute`).

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
│   └── routes/
│       ├── trigger.py          # POST /webhook/trigger
│       ├── execute.py          # POST /execute
│       ├── stream.py           # GET  /stream  (SSE)
│       ├── incident.py         # GET  /incident/{id}
│       └── slack.py            # POST /slack/interactions (optional)
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

### `POST /webhook/trigger`
Body: raw Datadog payload **or** internal `Alert`. Flow:
1. `map_datadog_payload()` → `Alert` (§1). Emit `log [SYSTEM] Alert received`.
2. Mark affected service `compromised`/`degraded`; emit `state`. Open incident
   (`status: diagnosing`); emit `incident`.
3. Run the brain → diagnosis (§3) + plan (§4); attach to incident; emit `incident`.
4. **Run the remediation engine** (auto phase): attempt `auto` steps, verify, and either
   resolve **or** escalate — emitting `log`/`state`/`incident` throughout.
5. Return `{ "incident_id": ... }`. Never blocks on human approval.

### `GET /stream` (SSE)
Long-lived `text/event-stream`. On connect, send current `state` immediately. Then forward
every pub/sub event as a **named** SSE event (`log`/`state`/`incident`). Use
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
| `EXECUTION_MODE` | `simulate` | `simulate` | `simulate \| real` — selects the executor. **The switch to real infra.** |
| `AUTO_REMEDIATE` | `true` | `true` | master switch for the auto-fix phase |
| `AUTO_REMEDIATE_MAX_SEVERITY` | `SEV-2` | `SEV-2` | incidents at/above this skip auto and escalate immediately |
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
- Trigger reliability flow: `curl -X POST localhost:8000/webhook/trigger -d @data/mock_alerts/bad_deploy.json -H 'Content-Type: application/json'` → `/stream` shows diagnose → auto rollback → verify → (resolve or escalate).
- Approve an escalated incident: `curl -X POST localhost:8000/execute -d '{...approve...}'` → state flips, incident `resolved`.
