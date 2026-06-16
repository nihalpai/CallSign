# Frontend (Next.js terminal UI)

> Scope: the visual proof. A two-panel "war room" that narrates the agents' work and
> shows infrastructure flip from compromised to isolated in real time. Consumes the SSE
> events from [data-contracts.md](data-contracts.md) §7.

## Responsibilities

- Fire the demo: a **Trigger Exploit** button → `POST /webhook/trigger`.
- Subscribe to `GET /stream` (SSE) and react to `log` / `state` / `incident` events.
- (Tier 0 only) show **Approve / Deny** buttons when an incident is awaiting approval →
  `POST /execute`. These disappear once voice (Tier 1) is the channel.
- Hold **no authoritative state** — it renders whatever the backend streams.

## Layout

```
┌───────────────────────────────┬───────────────────────────────┐
│  SYSTEM LOG (left)             │  INFRASTRUCTURE (right)        │
│  scrolling terminal            │  server tiles                  │
│                                │                                │
│ [SYSTEM] Alert received…       │  ┌─────────────┐  auth-01      │
│ [AGENT]  Cross-referencing…    │  │ COMPROMISED │  Auth  (red,  │
│ [AGENT]  Matched runbook…      │  └─────────────┘   blinking)   │
│ [SYSTEM] Requesting approval…  │  ┌─────────────┐  payment-gw   │
│ [VOICE]  "Do you approve…"     │  │  HEALTHY    │  Payments     │
│                                │  └─────────────┘               │
└───────────────────────────────┴───────────────────────────────┘
         [ Trigger Exploit ]      (Tier 0: [Approve] [Deny])
```

## Components

- `app/page.tsx` — layout, owns the SSE connection and shared state.
- `components/SystemLog.tsx` — append-only terminal. Each `log` event is a line, colored
  by `source` (`SYSTEM` dim, `AGENT` cyan, `VOICE` amber). Auto-scroll to bottom.
- `components/InfraPanel.tsx` — renders server tiles from the latest `state` event.
- `components/ServerTile.tsx` — one server; status drives style.
- `components/TriggerBar.tsx` — Trigger button + (Tier 0) Approve/Deny.

## State handling (no library needed)

```ts
const [logs, setLogs] = useState<LogEvent[]>([]);
const [servers, setServers] = useState<Server[]>([]);
const [incident, setIncident] = useState<Incident | null>(null);

useEffect(() => {
  const es = new EventSource(`${API}/stream`);
  es.addEventListener("log",      e => setLogs(l => [...l, JSON.parse(e.data)]));
  es.addEventListener("state",    e => setServers(JSON.parse(e.data).servers));
  es.addEventListener("incident", e => setIncident(JSON.parse(e.data)));
  return () => es.close();
}, []);
```

(Backend may send events as a single default stream with a `type` field, or as named SSE
events. Pick one and keep it consistent with [backend.md](backend.md) — named events are
cleaner with `EventSource`.)

## Server tile styling (status → visual)

| status        | label          | style |
|---------------|----------------|-------|
| `healthy`     | `[ HEALTHY ]`  | dim green border, steady |
| `compromised` | `[COMPROMISED]`| red, **blinking** (CSS pulse) |
| `isolated`    | `[ ISOLATED ]` | solid green, steady |

The flip `compromised → isolated` on the targeted tile is the demo's payoff — make the
transition obvious (color snap + brief flash). Optionally dim/highlight the blast-radius
servers when an incident is open.

## Aesthetic

Terminal / SOC console vibe: monospace, dark background, scanline-ish accents. Tailwind.
Keep it legible on a screen recording — large text, high contrast. Don't over-animate the
log; readability over flash.

## Approval buttons (Tier 0)

Render only when `incident?.status === "awaiting_approval"`. Approve/Deny POST the
execute body (data-contracts §6) using the live `incident_id`/`action`/`target`. Once
Tier 1 voice is the channel, hide these (or keep behind a `?dev` flag for fallback).

## Config
- `NEXT_PUBLIC_API_URL` → backend base (`http://localhost:8000`, or the ngrok URL in
  Phase 5). Used for both the SSE connection and POSTs.
