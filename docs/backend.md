# Backend (FastAPI)

> Scope: HTTP/SSE surface, in-memory state, wiring. The AI logic lives in
> [agents.md](agents.md); shapes in [data-contracts.md](data-contracts.md).

## Responsibilities

1. Accept the mock alert (`/webhook/trigger`).
2. Run the Lyzr Automata brain (callable function, no HTTP coupling).
3. Hold the infrastructure state in memory and mutate it.
4. Stream `log` / `state` / `incident` events to the UI over SSE (`/stream`).
5. Accept approval decisions from any channel (`/execute`).

## Project layout

```
backend/
├── app/
│   ├── main.py            # FastAPI app, route registration, CORS
│   ├── routes/
│   │   ├── trigger.py     # POST /webhook/trigger
│   │   ├── execute.py     # POST /execute
│   │   └── stream.py      # GET /stream  (SSE)
│   ├── brain/             # Lyzr Automata pipeline — see agents.md
│   │   ├── pipeline.py    # run(alert) -> (forensic_json, commander_obj)
│   │   ├── forensic.py    # Agent 1
│   │   └── commander.py   # Agent 2
│   ├── state.py           # in-memory infra state + mutations
│   ├── incidents.py       # incident registry (open/resolve)
│   ├── events.py          # SSE pub/sub (asyncio.Queue fan-out)
│   ├── models.py          # Pydantic models (mirror data-contracts.md)
│   └── config.py          # env, paths, .env loading
├── runbooks/              # 3 SOP .md files (RAG source)
├── data/
│   ├── infrastructure_state.json
│   └── mock_alerts/shellshock.json
├── requirements.txt
└── .env                   # LYZR_API_KEY, etc. (gitignored)
```

## Endpoints

### `POST /webhook/trigger`
Body: alert payload (data-contracts §1). Flow:
1. Emit `log`: `[SYSTEM] Alert received: <title>`.
2. Mark `host` server `compromised`; emit `state`.
3. Run the brain (emit `log` lines as each agent works — see agents.md).
4. Open an incident from the Commander output; emit `incident` (awaiting_approval).
5. Return `{ "incident_id": ... }`. (Approval arrives later via `/execute`.)

Trigger does **not** block on approval — it returns immediately; the UI shows the
awaiting-approval state and the chosen channel resolves it.

### `GET /stream`  (SSE)
Long-lived `text/event-stream`. On connect, immediately send the current `state` so a
late-joining browser is correct. Then forward every event from the pub/sub bus. Use
`sse-starlette`'s `EventSourceResponse` or a raw async generator over `StreamingResponse`.

### `POST /execute`
Body: execute request (data-contracts §6). Flow:
1. Resolve the incident (`approve`/`deny`); emit `incident` (resolved).
2. If `approve` + supported action → mutate state (e.g. status → `isolated`); emit
   `state`. If `deny` → emit `log` only.
3. Idempotent: a second call for an already-resolved incident is a no-op + warning log.

This is the **single entry point for every approval tier**. Keep it channel-agnostic.

## In-memory state (`state.py`)

- Load `infrastructure_state.json` once at import/startup into a module-level dict.
- Expose `get_state()`, `set_status(server_id, status)`, `blast_radius(server_id)`.
- Every mutation calls into `events.py` to publish a `state` event.
- No locks needed for the PoC (single worker, asyncio). Run uvicorn with `--workers 1`.

## SSE fan-out (`events.py`)

- Maintain a set of subscriber `asyncio.Queue`s.
- `publish(event)` puts the event on every queue.
- `/stream` registers a queue on connect, drains it in a loop, deregisters on
  disconnect. Helpers: `emit_log(source, message)`, `emit_state()`, `emit_incident(inc)`.

## CORS

Frontend runs on `:3000`, backend on `:8000`. Allow that origin (and the ngrok URL in
Phase 5) for both normal requests and the SSE endpoint.

## Config & secrets

- `.env` (gitignored): `LYZR_API_KEY`, optional `LYZR_*` ids. Load via `python-dotenv`.
- If `LYZR_API_KEY` is missing, the brain falls back to a **static canned script** so the
  loop still demos — log a clear `[SYSTEM]` warning when this happens.

## requirements.txt (starting point)

```
fastapi
uvicorn[standard]
sse-starlette
pydantic
python-dotenv
httpx
lyzr-automata      # Lyzr Automata SDK (confirm exact package name)
```

## Local checks per phase

- Phase 1: `curl -X POST localhost:8000/webhook/trigger -d @data/mock_alerts/shellshock.json -H 'Content-Type: application/json'` → 200 + parsed echo.
- Phase 3: trigger, watch `/stream` (`curl -N localhost:8000/stream`) emit logs, then
  `curl -X POST localhost:8000/execute -d '{...approve...}'` → state event flips status.
