# Frontend (Next.js terminal UI)

> Scope: the visual proof — an **approvals dashboard** showing a live queue of pending requests
> from any source, plus a request/incident **detail** view that points the approver exactly at the
> problem. Consumes the SSE events from [data-contracts.md](data-contracts.md) §7.

> **v2 added:** an exact-location / remediation-plan panel, escalation status, an `EXECUTION_MODE`
> banner, generalized action buttons, and a deep-linkable `/incident/{id}` route.

> **v3 reframe:** the war-room becomes a generic **approvals dashboard** — a queue of pending
> ApprovalRequests (§10) from any requester (external agents *and* incidents), each with action,
> context/blast-radius, and Approve/Deny. The incident detail is one request type's richer view. It
> now also surfaces **triage output** (diagnosed location, probable cause, suggested action) and
> **who it routed to**. Driven by the new `approval` SSE event alongside `incident`.

## Responsibilities

- Show a **pending-approvals queue** — every open ApprovalRequest (§10) from any source, with action,
  risk, and who it's waiting on.
- Fire demos: a **Simulate Alert** picker → `POST /webhook/trigger` (the incident vertical), and/or a
  toy agent hitting `POST /approvals` (the generic gate). *(Demo/test injectors; in production Datadog
  or a real agent hits the same endpoints.)*
- Subscribe to `GET /stream` and react to `log` / `state` / `incident` / `approval`.
- Render the **request detail**: action + context, the **triage output** (location, probable cause,
  suggested action) when present, **who it routed to**, the ordered plan with per-step status (incident
  vertical), and Approve/Deny buttons when a decision is needed.
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
- `components/TriggerBar.tsx` — Simulate-Alert picker + the approver action buttons.
- `components/ModeBanner.tsx` — `incident.execution_mode` → **SIMULATED** vs **LIVE** banner.
- `components/ApprovalsQueue.tsx` — the pending-requests list (from the `approval` events); click a
  row → its detail view.
- `components/TriagePanel.tsx` — when present, the diagnosed location + probable cause + suggested
  action (§13) and **routed-to** (matched expert or "on-call fallback"); read-only context for the
  approver. See [triage.md](triage.md).

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
const [approvals, setApprovals] = useState<Record<string, ApprovalRequest>>({}); // keyed by request_id

useEffect(() => {
  const es = new EventSource(`${API}/stream`);
  es.addEventListener("log",      e => setLogs(l => [...l, JSON.parse(e.data)]));
  es.addEventListener("state",    e => setServers(JSON.parse(e.data).servers));
  es.addEventListener("incident", e => setIncident(JSON.parse(e.data)));   // full §5 object
  es.addEventListener("approval", e => {                                   // §10 + status/decision
    const a = JSON.parse(e.data); setApprovals(m => ({ ...m, [a.request_id]: a }));
  });
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

Render when a request is awaiting a decision (`incident.status === "awaiting_approval"`, or an
ApprovalRequest in `awaiting_approval`). The button label/action come from the requested action (or
the **current step needing approval** in the incident vertical — e.g. *Approve Rollback*). They POST
`/execute` (§6) with the live `incident_id`/`request_id`, `action`/`target`, and `actor` = the
approver. These stay as a visible UI fallback even when Slack/voice is the primary channel.

## Aesthetic
SOC/terminal console: monospace, dark, high contrast, legible on a screen recording.
Tailwind. Readability over flash; don't over-animate the log.

## Config
- `NEXT_PUBLIC_API_URL` → backend base (`http://localhost:8000`, or the ngrok URL). Used for
  the SSE connection, POSTs, and the `/incident/{id}` fetch.
