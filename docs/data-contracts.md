# Data contracts

**Single source of truth for every shape that crosses a boundary.** Change a schema here
first, then update producers/consumers. No other doc redefines a shape — they reference a
section number.

> **v1 → v2 note.** v1 (the proven PoC) handled *security* incidents: alert → diagnosis →
> single `isolate_container` action → button approval. v2 generalizes to **reliability**
> incidents too (bad deploy, error spike, latency), adds an **ordered remediation plan**,
> **autonomous safe-step execution**, and **Slack + voice escalation to an on-call
> engineer**. The security scenario is preserved as one `incident_type`. Sections marked
> *(expanded)* / *(revised)* changed in v2; the core numbering (§3 = Agent 1, §4 = Agent 2,
> §6 = /execute) is unchanged so existing references stay valid.

---

## 1. Inbound alert (internal `Alert`)

POSTed to `/webhook/trigger`. The canonical internal shape. Mock fixtures live at
`backend/data/mock_alerts/*.json`. A real Datadog webhook is mapped onto this (see §1b).

```json
{
  "alert_id": "dd-2026-0042",
  "title": "5xx error rate spike on checkout",
  "alert_type": "reliability",
  "priority": "P1",
  "tags": ["service:payment-gw", "host:payment-gw", "route:/api/checkout", "deploy:dpl_9f2"],
  "body": "HTTP 5xx on /api/checkout jumped to 40% immediately after deploy dpl_9f2.",
  "host": "payment-gw",
  "timestamp": "2026-06-15T09:14:00Z"
}
```

Fields the brain relies on: `tags` (carries `service:`, `host:`, `route:`, `deploy:`,
and for security `cve:`), `priority`, `body`, `host`. The security fixture
(`shellshock.json`) is the same shape with `alert_type: "security"` and a `cve:` tag.

---

## 1b. Raw Datadog webhook → `Alert` mapping  *(new in v2)*

Datadog **Webhook** notifications send a JSON body **you define** in the integration
config using template variables. We define the template to land close to §1. See
[datadog.md](datadog.md) for setup.

Template body configured in Datadog:
```json
{
  "alert_id": "$ID",
  "title": "$EVENT_TITLE",
  "alert_type": "reliability",
  "priority": "$PRIORITY",
  "tags": ["$TAGS"],
  "body": "$EVENT_MSG",
  "host": "$HOSTNAME",
  "timestamp": "$DATE"
}
```

Mapping rules applied in `trigger.py` (`map_datadog_payload`):

| Datadog var | → internal `Alert` field | Notes |
|-------------|--------------------------|-------|
| `$ID` | `alert_id` | |
| `$EVENT_TITLE` | `title` | |
| `$PRIORITY` | `priority` | `P1…P5`; missing → `P3` |
| `$TAGS` | `tags` | comma string → list; we read `service:`/`host:`/`route:`/`deploy:`/`cve:` |
| `$EVENT_MSG` | `body` | |
| `$HOSTNAME` | `host` | falls back to the `host:`/`service:` tag if absent |
| `$DATE` | `timestamp` | normalized to ISO-8601 UTC |

Unknown/extra fields are ignored. The mapper is the **only** Datadog-aware code; the rest
of the system sees only §1.

---

## 2. Infrastructure state (blast-radius graph)

`backend/data/infrastructure_state.json`. Loaded into memory at startup; mutated in
place. Server `id` is the universal key (alerts, agent output, UI tiles).

```json
{
  "servers": [
    { "id": "auth-01",    "name": "Auth Server",     "service": "Authentication", "status": "healthy", "depended_on_by": ["payment-gw", "web-01"], "container": "auth-svc-prod" },
    { "id": "payment-gw", "name": "Payment Gateway",  "service": "Payments",       "status": "healthy", "depended_on_by": ["web-01"],               "container": "payments-svc-prod" },
    { "id": "web-01",     "name": "Web Frontend",     "service": "Web",            "status": "healthy", "depended_on_by": [],                       "container": "web-svc-prod" },
    { "id": "db-01",      "name": "Primary Database", "service": "Postgres",       "status": "healthy", "depended_on_by": ["auth-01", "payment-gw"], "container": "pg-primary-prod" }
  ]
}
```

**Status enum *(expanded in v2)*:** `healthy | compromised | isolated | degraded | rolled_back | recovered`.
- `compromised` (security) / `degraded` (reliability) — something is wrong.
- `isolated` (taken out of rotation) / `rolled_back` (reverted to prior deploy) — remediated.
- `recovered` — verified healthy again after remediation.

**Blast radius** for a server = transitive closure of `depended_on_by` (who breaks if it
goes down). Reported by Agent 1; highlighted by the UI.

---

## 2b. Deployments state  *(new in v2)*

`backend/data/deployments.json`. Gives `rollback_deployment` something to roll back to.
In **simulate** mode rollback swaps `current` ↔ `previous`; in **real** mode the executor
calls the provider API (see [remediation.md](remediation.md)).

```json
{
  "deployments": [
    {
      "service": "payment-gw",
      "current":  { "deploy_id": "dpl_9f2", "commit": "a1b2c3d", "deployed_at": "2026-06-15T09:05:00Z", "healthy": false },
      "previous": { "deploy_id": "dpl_8e1", "commit": "f9e8d7c", "deployed_at": "2026-06-14T18:00:00Z", "healthy": true }
    }
  ]
}
```

---

## 3. Diagnosis — Agent 1 "Diagnostician" output  *(revised in v2)*

Agent 1 **must** return strict JSON (no prose). Pure analysis — it does *not* pick the
action (that's Agent 2's plan). The contract Agent 2 and the backend parse.

```json
{
  "incident_type": "bad_deploy",
  "severity": "SEV-1",
  "affected_service": "payment-gw",
  "exact_location": {
    "service": "payment-gw",
    "route": "/api/checkout",
    "deploy_id": "dpl_9f2",
    "commit": "a1b2c3d",
    "datadog_link": "https://app.datadoghq.com/event/jump_to?event_id=..."
  },
  "blast_radius": ["web-01"],
  "runbook": "Bad-Deploy-Rollback.md",
  "confidence": 0.86,
  "summary": "5xx on /api/checkout spiked to 40% immediately after deploy dpl_9f2.",
  "rationale": "Error onset aligns exactly with deploy dpl_9f2; runbook prescribes rollback.",
  "cve": null
}
```

- **`incident_type` enum:** `security | bad_deploy | error_spike | latency | crash_loop | resource_exhaustion`.
- `exact_location` is what points the engineer **exactly where** the problem is (UI + Slack
  show it, `datadog_link` deep-links the event).
- `cve` is non-null only for `incident_type: security`.
- `affected_service` / every id referenced is a server `id` from §2.

---

## 4. Remediation plan + script — Agent 2 "Strategist" output  *(revised in v2)*

Agent 2 turns the diagnosis into an **ordered, multi-step** plan plus the spoken/Slack
approval script. (v1's single-action "Commander" output is folded into this.)

```json
{
  "summary": "Roll back Payments to the last good deploy; restart if needed; isolate as last resort.",
  "steps": [
    { "action": "rollback_deployment", "target": "payment-gw", "autonomy": "auto",  "reversible": true, "description": "Promote previous good deploy dpl_8e1" },
    { "action": "restart_service",      "target": "payment-gw", "autonomy": "auto",  "reversible": true, "description": "Restart workers after rollback" },
    { "action": "isolate_service",      "target": "payment-gw", "autonomy": "human", "reversible": true, "description": "Remove from rotation if rollback fails" }
  ],
  "script": "Severity one: checkout is failing for forty percent of users right after the last deploy to Payments. I can roll it back to the previous good version. Do you approve the rollback?"
}
```

- **`steps`** run in order. **`autonomy`**: `auto` = CallSign may run it itself (safe,
  reversible); `human` = needs an engineer's yes. See the policy in [remediation.md](remediation.md).
- **`script`** hard rules (unchanged from v1): **≤ 3 sentences, ends in a yes/no question**,
  spoken register ("Severity one", not "SEV-1"), no markdown. Used by voice **and** the
  Slack card. See [agents.md](agents.md).

---

## 4b. Remediation action catalog  *(new in v2)*

Closed enum. Each action's simulate-vs-real behavior is defined in
[remediation.md](remediation.md); this table is the authoritative list.

| action | meaning | typical `incident_type` | reversible |
|--------|---------|--------------------------|------------|
| `rollback_deployment` | revert service to its previous deploy | bad_deploy | yes |
| `restart_service` | restart the service/workers | crash_loop, error_spike | yes |
| `isolate_service` | remove from load-balancer rotation | error_spike, security | yes |
| `scale_up` | add capacity | resource_exhaustion, latency | yes |
| `disable_feature` | turn off a feature flag | bad_deploy, error_spike | yes |
| `isolate_container` | sever container network (security) | security | yes |
| `quarantine_host` | cut a host off the network | security | yes |
| `revoke_keys` | deactivate leaked credentials | security | yes |

---

## 5. Incident object  *(expanded in v2)*

Backend-internal, channel-agnostic. Created at trigger; mutated through its lifecycle;
the latest version is pushed to the UI on every `incident` SSE event (§7).

```json
{
  "incident_id": "inc-7f3a",
  "status": "awaiting_approval",
  "execution_mode": "simulate",
  "diagnosis": { "...": "§3" },
  "plan": { "...": "§4" },
  "attempts": [
    { "action": "rollback_deployment", "target": "payment-gw", "actor": "auto", "result": "failed", "ts": "2026-06-15T09:14:05Z" }
  ],
  "assigned_engineer": { "id": "eng-02", "name": "Priya", "channels": ["slack", "voice"] },
  "decision": null,
  "created_at": "2026-06-15T09:14:03Z"
}
```

- **`status` lifecycle:** `received → diagnosing → remediating → verifying →` then either
  `resolved` (auto-fix worked) **or** `escalated → awaiting_approval → resolved | failed`.
- `execution_mode`: `simulate | real` (the `EXECUTION_MODE` toggle, §config in
  [backend.md](backend.md)). Shown in the UI banner.
- `attempts[]`: every action tried, with `actor` (`auto | <engineer_id> | voice`) and
  `result` (`succeeded | failed | denied`).
- `assigned_engineer`: `null` until escalation; set from the on-call registry (§8).

---

## 6. `/execute` request — any approval channel → backend  *(expanded in v2)*

The one call every channel makes: UI button, Lyzr voice tool, Slack action, **and** the
internal auto-remediation engine. Identical body.

```json
{
  "incident_id": "inc-7f3a",
  "decision": "approve",
  "action": "rollback_deployment",
  "target": "payment-gw",
  "actor": "voice"
}
```

- `decision`: `approve | deny`. `action`: any §4b action. `actor`: `auto | <engineer_id> | voice`.
- On `approve`: the **Remediation Engine** runs the action via the active executor
  (simulate/real), updates §2 status, appends to `attempts`, emits `state` + `incident` +
  a closing `log`. On `deny`: log only, `status → failed` (or re-escalate per policy).
- Idempotent: a second call on a resolved incident is a no-op + warning log.

---

## 7. SSE events — backend → browser  *(extended in v2)*

`GET /stream`. Named events; the UI switches on event name.

```jsonc
// "log" — one terminal line
{ "type": "log", "data": {
    "source": "REMEDIATION",        // SYSTEM | AGENT | REMEDIATION | SLACK | VOICE
    "message": "Auto-remediation: rolling back payment-gw to dpl_8e1…",
    "ts": "2026-06-15T09:14:05Z"
}}

// "state" — full current infra state (UI re-renders all tiles)
{ "type": "state", "data": { "servers": [ /* §2 */ ] }}

// "incident" — incident created or updated (carries the full §5 object)
{ "type": "incident", "data": { /* §5 */ }}
```

The UI keeps the latest `state` and `incident`, and appends every `log`. The incident's
`status` drives the UI (auto-remediation activity, escalation status, approve/deny buttons).

---

## 8. On-call engineer registry  *(new in v2)*

`backend/data/on_call.json`. Static schedule. Selection logic in [escalation.md](escalation.md).

```json
{
  "engineers": [
    { "id": "eng-01", "name": "Alex",  "slack_id": "U01ALEX", "phone": "+15555550101", "timezone": "America/New_York", "shift_start": "09:00", "shift_end": "21:00", "status": "active" },
    { "id": "eng-02", "name": "Priya", "slack_id": "U02PRIYA","phone": "+15555550102", "timezone": "Asia/Kolkata",      "shift_start": "21:00", "shift_end": "09:00", "status": "active" }
  ]
}
```

- **"awake & available"** = `status == "active"` **and** current local time (per `timezone`)
  falls within `[shift_start, shift_end)` (wrapping past midnight). First match wins; tie-break
  by order. If none match, escalate to the first `active` engineer and log that it's off-hours.

---

## 9. Slack incident card  *(new in v2)*

Block Kit message CallSign posts to the on-call engineer (DM or channel). Carries the
exact location and a deep-link into the CallSign UI. See [slack.md](slack.md).

```json
{
  "channel": "U02PRIYA",
  "text": "🚨 SEV-1 incident on Payments — approval needed",
  "blocks": [
    { "type": "header", "text": { "type": "plain_text", "text": "🚨 SEV-1 · Payments (payment-gw)" } },
    { "type": "section", "text": { "type": "mrkdwn", "text": "*Where:* `/api/checkout` · deploy `dpl_9f2` (`a1b2c3d`)\n*What:* 5xx at 40% since the last deploy\n*Auto-remediation:* rollback failed — your call needed" } },
    { "type": "section", "text": { "type": "mrkdwn", "text": "*Proposed:* roll back to `dpl_8e1`" } },
    { "type": "actions", "elements": [
      { "type": "button", "style": "primary", "text": { "type": "plain_text", "text": "Open CallSign" }, "url": "https://<ui>/incident/inc-7f3a" }
    ]}
  ]
}
```

Optional interactive Approve/Deny buttons (Slack → `/slack/interactions`) are described in
[slack.md](slack.md); the primary approval path is the CallSign UI link + the voice call.

---

## Field-naming rules

- snake_case everywhere on the wire (Python-friendly; the frontend adapts).
- Server `id` is the only join key — never match on display `name`.
- Timestamps are ISO-8601 UTC strings.
- Enums are closed; an unknown value is a contract violation, not a free-text passthrough.
