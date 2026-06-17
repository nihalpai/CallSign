# Frontend (Next.js terminal UI)

> Scope: the visual proof — a "war room" that narrates the agents + remediation engine and
> shows infrastructure recover in real time, and an **incident detail** view that points the
> engineer exactly where the problem is. Consumes the SSE events from
> [data-contracts.md](data-contracts.md) §7.

> **v2 additions:** an exact-location / remediation-plan panel, auto-remediation + escalation
> status, an `EXECUTION_MODE` banner, generalized action buttons (Rollback / Isolate / …),
> and a deep-linkable `/incident/{id}` route for the Slack card.

## Responsibilities

- Fire demos: a **Simulate Alert** picker → `POST /webhook/trigger` (choose the scenario;
  see "Scenario picker"). *(This replaces v1's single "Trigger Exploit" — it's a demo/test
  injector; in production Datadog hits the same endpoint.)*
- Subscribe to `GET /stream` and react to `log` / `state` / `incident`.
- Render the **incident detail**: exact location, the ordered plan with per-step status,
  who was paged/called, and the engineer's action buttons when approval is needed.
- Hold **no authoritative state** — render whatever the backend streams.

## Layout

```
┌───────────────────────────── EXECUTION_MODE: SIMULATED ─────────────────────────────┐
├───────────────────────────────┬──────────────────────────────────────────────────────┤
│  SYSTEM LOG (left)            │  INFRASTRUCTURE (right)                                │
│  scrolling terminal           │  service tiles (healthy/degraded/rolled_back/…)        │
│ [SYSTEM] Alert received…      │  ┌─────────────┐ payment-gw  ┌─────────────┐ web-01    │
│ [AGENT]  bad_deploy on…       │  │  DEGRADED   │ Payments    │  HEALTHY    │ Web        │
│ [REMEDIATION] rollback…       │  └─────────────┘ (blast)     └─────────────┘            │
│ [REMEDIATION] verify: failed  │ ────────────────────────────────────────────────────── │
│ [SYSTEM] Escalating to Priya  │  INCIDENT inc-7f3a                                      │
│ [VOICE]  Calling Priya…       │  Where: /api/checkout · deploy dpl_9f2 (a1b2c3d) [DD↗] │
│                               │  Plan:  ① rollback_deployment  ✗ failed                 │
│                               │         ② restart_service       · pending               │
│                               │         ③ isolate_service  ⚠ needs you                  │
│                               │  Paged: Priya (Slack + call)                            │
└───────────────────────────────┴──────────────────────────────────────────────────────┘
   [ Simulate Alert ▼ ]                                   [ Approve ] [ Deny ]
```

## Components

- `app/page.tsx` — owns the SSE connection + shared state; the war-room layout.
- `app/incident/[id]/page.tsx` — deep-link target for the Slack card; fetches `GET
  /incident/{id}` then subscribes to `/stream` for live updates.
- `components/SystemLog.tsx` — append-only terminal; color by `source`
  (`SYSTEM` dim · `AGENT` cyan · `REMEDIATION` violet · `SLACK` green · `VOICE` amber); auto-scroll.
- `components/InfraPanel.tsx` / `ServerTile.tsx` — service tiles from latest `state`.
- `components/IncidentDetail.tsx` — exact location (+ `datadog_link`), the plan timeline
  with per-step status, and the escalation/paging status, from the latest `incident`.
- `components/PlanTimeline.tsx` — the ordered `plan.steps` annotated with `attempts` results
  (succeeded ✓ / failed ✗ / pending · / needs-you ⚠).
- `components/TriggerBar.tsx` — Simulate-Alert picker + the engineer action buttons.
- `components/ModeBanner.tsx` — `incident.execution_mode` → **SIMULATED** vs **LIVE** banner.

## Scenario picker (answers "how do I trigger the other issues")

The picker sends a different mock alert per scenario; the backend's brain routes each to the
right runbook + plan:

| Scenario | mock alert | →  plan first step |
|----------|-----------|--------------------|
| Bad deploy (checkout 5xx) | `bad_deploy.json` | `rollback_deployment` |
| Error spike | `error_spike.json` | `restart_service` / `disable_feature` |
| Shellshock RCE (security) | `shellshock.json` | `isolate_container` |

## State handling (no library needed)

```ts
const [logs, setLogs] = useState<LogEvent[]>([]);
const [servers, setServers] = useState<Server[]>([]);
const [incident, setIncident] = useState<Incident | null>(null);

useEffect(() => {
  const es = new EventSource(`${API}/stream`);
  es.addEventListener("log",      e => setLogs(l => [...l, JSON.parse(e.data)]));
  es.addEventListener("state",    e => setServers(JSON.parse(e.data).servers));
  es.addEventListener("incident", e => setIncident(JSON.parse(e.data)));   // full §5 object
  return () => es.close();
}, []);
```

## Service tile styling (status → visual)

| status | label | style |
|--------|-------|-------|
| `healthy` | `[ HEALTHY ]` | dim green, steady |
| `degraded` / `compromised` | `[ DEGRADED ]` / `[COMPROMISED]` | red/amber, **blinking** |
| `isolated` | `[ ISOLATED ]` | grey, steady |
| `rolled_back` | `[ROLLED BACK]` | blue, steady |
| `recovered` | `[ RECOVERED ]` | solid green flash |

The degraded → recovered (or rolled_back) flip on the affected tile is the payoff — make it
obvious. Highlight blast-radius tiles while the incident is open.

## Action buttons (the human channel)

Render when `incident.status === "awaiting_approval"`. The button label/action come from the
**current step needing approval** (e.g. *Approve Rollback*, *Approve Isolate*). They POST
`/execute` (§6) with the live `incident_id`/`action`/`target` and `actor` = the engineer.
When the channel is voice-only, these can stay as a visible fallback.

## Aesthetic
SOC/terminal console: monospace, dark, high contrast, legible on a screen recording.
Tailwind. Readability over flash; don't over-animate the log.

## Config
- `NEXT_PUBLIC_API_URL` → backend base (`http://localhost:8000`, or the ngrok URL). Used for
  the SSE connection, POSTs, and the `/incident/{id}` fetch.
