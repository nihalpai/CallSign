# CallSign harness — fake-agent test scripts

Small throwaway scripts that pretend to be external AI agents calling the approval
gate. They double as the **manual end-to-end checklist** and the **demo**. No cloud
accounts are needed — the backend runs in simulate mode throughout.

## Scripts

| Script | Mode | Wait | Diagnostics | What it exercises |
|---|---|---|---|---|
| `refund_bot.py` | callback | blocking | none | Plain gate: simplest path, mode=callback, synchronous |
| `delete_bot.py` | callback | async | none | Async path: local callback listener (or polling fallback) |
| `error_with_logs_bot.py` | gate | blocking | stack trace + deploys | Smart triage: diagnosis, expertise routing, gate executor |
| `trigger_incident.sh` | — | — | — | Incident vertical: Datadog-shaped alert → `/webhook/trigger` |

### refund_bot.py

A fake support agent that asks to "Refund $5,000 to customer 8831". Uses
`mode=callback` (the agent would run the refund itself on approval) and
`wait=blocking` (holds the HTTP connection until a human decides). On approval it
prints a simulated refund confirmation; on deny it explains why it skipped.

### delete_bot.py

A fake analytics-cleanup agent that asks to "Delete 14,000 stale records". Uses
`wait=async` so the HTTP request returns immediately with a `request_id`. The bot
starts a tiny stdlib HTTP listener on `localhost:9731` to receive the CallSign
callback POST. If the port cannot bind (e.g. already in use) it falls back to
polling `GET /approvals/{id}` — the script logs which path it took.

### error_with_logs_bot.py

A fake observability agent that asks to `rollback_deployment` on `payment-gw`. It
attaches a realistic Python stack trace and a list of recent deploys under
`diagnostics`. This is the headline demo: CallSign enriches the request (pinpoints
the error in the trace, correlates with deploy `dpl_9f2`), routes to the payment
area owner, and the human sees a pre-diagnosed Slack card. Uses `mode=gate` so
CallSign runs the rollback through its (simulated) executor on approval.

### trigger_incident.sh

A `curl` one-liner that POSTs `backend/data/mock_alerts/bad_deploy.json` to
`/webhook/trigger` (the incident vertical). This exercises the Datadog-shaped
ingestion path. Watch the approvals dashboard and (if `SLACK_ENABLED=true`) your
Slack workspace for the resulting card.

---

## Environment variables

| Variable | Default | Required |
|---|---|---|
| `APPROVAL_API_KEY` | — | **yes** |
| `CALLSIGN_BASE_URL` | `http://localhost:8000` | no |
| `CALLBACK_PORT` | `9731` | no (delete_bot only) |

---

## Full E2E pass (one sitting)

Follow these steps to exercise every feature in simulate mode — no cloud accounts
needed. This mirrors the checklist in `docs/testing.md`.

### 0 — Prerequisites

```bash
# Install harness dependencies (httpx is the only one, likely already installed)
pip install -r harness/requirements.txt
```

### 1 — Start the backend in simulate mode

```bash
cd backend
cp .env.example .env          # if .env doesn't exist yet
# Ensure these are set in .env (defaults are safe):
#   EXECUTION_MODE=simulate
#   AUTO_REMEDIATE=false
#   ENRICH_REQUESTS=true
#   EXPERTISE_ROUTING=true
#   SLACK_ENABLED=false       # set true + add SLACK_BOT_TOKEN for a real card
uvicorn app.main:app --reload
```

Export your key in a second terminal (keep the backend running):

```bash
export APPROVAL_API_KEY=<value from .env>
export CALLSIGN_BASE_URL=http://localhost:8000
```

### 2 — Open the dashboard

```bash
cd frontend && npm run dev      # http://localhost:3000
```

Open `http://localhost:3000` in a browser — you will see approval requests appear
live as the scripts run.

### 3 — Run error_with_logs_bot (smart triage, headline demo)

```bash
python harness/error_with_logs_bot.py
```

The script blocks. In a **third terminal**, approve the request:

```bash
# Find the request_id from the script output or GET /approvals
curl -s http://localhost:8000/approvals \
  -H "X-API-Key: $APPROVAL_API_KEY" | python3 -m json.tool

# Approve it (replace <id> with the actual request_id)
curl -s -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $APPROVAL_API_KEY" \
  -d '{"request_id":"<id>","decision":"approve","actor":"eng-01"}'
```

The bot prints the outcome and exits. The dashboard flips to "approved".

### 4 — Run refund_bot (plain blocking gate)

```bash
python harness/refund_bot.py
```

Approve or deny via the dashboard or the same `curl /execute` above. The bot prints
"→ issuing refund (simulated)" on approval.

### 5 — Run delete_bot (async + callback)

```bash
python harness/delete_bot.py
```

The bot prints "Callback listener up" (or "Falling back to polling") and waits.
Approve as before. The decision arrives over the callback POST and the bot prints
the outcome.

### 6 — Fire the incident vertical

```bash
./harness/trigger_incident.sh
```

This POSTs the canned bad_deploy alert. Watch the dashboard for a new request and
(if `SLACK_ENABLED=true`) a Slack card.

### 7 — Optional: test opt-in auto-approve

Flip `AUTO_REMEDIATE=true` in `.env`, restart the backend, and run `refund_bot.py`
again. The request resolves without a human click.

### 8 — Optional: test 401 auth

```bash
curl -X POST http://localhost:8000/approvals \
  -H "Content-Type: application/json" \
  -H "X-API-Key: WRONG_KEY" \
  -d '{"action":"test","mode":"callback","wait":"blocking"}'
# Expect: 401 Unauthorized
```

---

## Notes

- All scripts are **syntax-checked** at CI time via `python -m py_compile`.
- Full runs require the backend (`uvicorn app.main:app --reload`) to be up.
- `delete_bot.py` starts a callback listener on port `9731` by default; set
  `CALLBACK_PORT` to change it.
- Scripts exit non-zero on connection errors, auth failures, and timeouts.

---

For a realistic example of wiring a real AI agent (not a fake harness script) to the gate,
see `examples/geo_agent.py` and `examples/WIRING.md`.
