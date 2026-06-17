# Datadog ingestion

> Scope: getting a real production incident from the monitored app ("Don Draper") into
> CallSign. The mapping shape is [data-contracts.md](data-contracts.md) §1b. This is the
> headline of the long-term demo, and it's the part with the most moving pieces — so the
> system is built to run **with or without** Datadog.

## The flow

```
Don Draper (prod)  ──► Datadog Agent / APM watches it
   │  you induce a fault (throw 5xx, spike latency, ship a bad deploy)
   ▼
Datadog Monitor crosses its threshold  ──► Webhook notification
   ▼
ngrok https URL  ──►  POST {PUBLIC_BACKEND_URL}/webhook/trigger   (CallSign)
   ▼
map_datadog_payload() → internal Alert (§1) → the rest of CallSign is unchanged
```

## Build-and-test WITHOUT Datadog first (important)

`/webhook/trigger` already accepts the §1 shape, and the Datadog template (§1b) maps onto
it. So the **entire integration is built and tested with a `curl`** that mimics Datadog —
no account required:

```
curl -X POST {PUBLIC_BACKEND_URL}/webhook/trigger \
  -H 'Content-Type: application/json' \
  -d @backend/data/mock_alerts/bad_deploy.json
```

Only after the loop is solid do you point real Datadog at the same URL. This keeps Datadog
off the critical path for the build.

## Datadog setup (when wiring it for real)

1. **Account:** the truly-free tier is limited; **Webhooks + custom Monitors generally need
   the Pro plan — use the 14-day Pro free trial.** (Verify current limits at signup.)
2. **Instrument Don Draper:** install the Datadog Agent on the host, or add APM, so error
   rate / latency / deploy events flow in.
3. **Create a Monitor** on the symptom you'll demo (e.g. `5xx rate > 10% for 1m` on the
   checkout service).
4. **Webhook integration:** Integrations → Webhooks → add one whose URL is your
   `{PUBLIC_BACKEND_URL}/webhook/trigger` and whose **payload body is the §1b template**
   (so the fields map cleanly). Add tags on the monitor (`service:`, `host:`, `route:`,
   `deploy:`) — the mapper reads these.
5. **Notify the webhook** from the monitor message (`@webhook-callsign`).

## ngrok — make the local backend reachable

Datadog's cloud can't reach `localhost`. Expose it:
```
ngrok http 8000        # free tier; use the https URL as PUBLIC_BACKEND_URL
```
Put that origin in CORS ([backend.md](backend.md)) and as the webhook URL.

## The mapper

`map_datadog_payload(raw) -> Alert` is the **only** Datadog-aware code (lives in
`trigger.py` or `app/integrations/datadog.py`). Rules in §1b. Everything downstream sees
only the internal `Alert`, so swapping Datadog for another source later means rewriting just
this function.

## Inducing the demo fault (Don Draper)

Pick whatever is easy to trigger and revert:
- ship a deliberately broken deploy (→ `incident_type: bad_deploy` → `rollback_deployment`),
- a route that throws 5xx behind a feature flag (→ `error_spike` → `disable_feature`/`restart`),
- a latency injection (→ `latency` → `scale_up`).

Map each to a runbook so Agent 1 can ground its diagnosis (see [agents.md](agents.md)).

## Out of scope now
- Standing up the Datadog account, agent install, real monitors. Documented; the
  `curl`-with-template path is what makes this buildable today.
