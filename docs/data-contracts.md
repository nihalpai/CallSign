# Data contracts

**Single source of truth for every shape that crosses a boundary.** Change a schema here
first, then update producers/consumers. No other doc redefines a shape — they reference a
section number.

> **Slim-build note (2026-06).** The build was narrowed to the pure **approval gate**.
> Incident-specific shapes (§1 Alert, §1b Datadog mapping, §2 infra state, §2b deployments,
> §3 Diagnostician output, §4 Strategist plan, §4b action catalog, §5 Incident object, §6 /execute
> body, §9 Slack incident card) and the diagnosis shapes (§13, §13b) are **no longer actively
> maintained**. They are preserved below for reference but are not required for the core gate.
> **The active shapes are §10 (ApprovalRequest), §11 (Decision outcome), and §12 (Requester).**

> **v1 → v2 note.** v1 (the proven PoC) handled *security* incidents: alert → diagnosis →
> single `isolate_container` action → button approval. v2 generalizes to **reliability**
> incidents too (bad deploy, error spike, latency), adds an **ordered remediation plan**,
> **autonomous safe-step execution**, and **Slack + voice escalation to an on-call
> engineer**. The security scenario is preserved as one `incident_type`. Sections marked
> *(expanded)* / *(revised)* changed in v2; the core numbering (§3 = Agent 1, §4 = Agent 2,
> §6 = /execute) is unchanged so existing references stay valid.

> **v2 → v3 reframe (the approval gate).** v3 makes the **approval request** (§10) the core
> object: *any* external AI agent can ask CallSign to get a human's yes/no before a high-stakes
> action. **Two concepts to keep straight:**
> - **`ApprovalRequest` (§10)** — the generic inbound shape any caller POSTs to `/approvals`.
> - **`Alert` (§1)** — one *requester* (the incident vertical): the incident pipeline maps an
>   Alert into an ApprovalRequest and uses the brain (§3/§4) to enrich it.
>
> So the `Incident` object (§5) is the incident-vertical *specialization* of a generic request.
> The brain (§3/§4) is now **optional enrichment** that *informs* the human — it never decides
> approve/deny. Autonomy (auto-approve) is opt-in and OFF by default. Single-tenant for now;
> multi-tenant fields are marked FUTURE.

---

## 1. Inbound alert (internal `Alert`)

POSTed to `/webhook/trigger`. The canonical internal shape. Mock fixtures live at
`backend/data/mock_alerts/*.json`. A real Datadog webhook is mapped onto this (see §1b).

> An `Alert` is **one requester** (the incident vertical). The incident pipeline maps it into a
> generic `ApprovalRequest` (§10) and runs the brain (§3/§4) to enrich it. Other requesters
> (external agents via the SDK) POST §10 directly.

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

> **v3 role:** this is **enrichment output** for the incident vertical — it *informs* the human
> so they can decide fast. It never decides approve/deny. For raw approval requests (§10) that
> arrive pre-scoped, enrichment can be skipped (`ENRICH_REQUESTS=false`). When a caller sends
> logs instead of an alert, Agent 1 can also produce the diagnosis-from-logs output (§13).

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

> **v3 role:** also enrichment — it proposes the *suggested action* the human approves. It does
> not act on its own; a human (or, if explicitly enabled, an opt-in auto-approve below a risk
> threshold) authorizes every step. See [remediation.md](remediation.md).

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

> **v3:** the Incident is the incident-vertical *specialization* of a generic approval request.
> The generic request lifecycle is: `created → (enriching) → awaiting_approval →
> approved | denied | timed_out →` then `executed` (gate mode) **or** `returned` (callback mode).
> The incident `status` values below are the vertical's richer names for those same stages.

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

The one call every **approval channel** makes: UI button, Lyzr voice tool, Slack action, **and**
the internal auto-remediation engine. Identical body. This stays the internal **decision sink**:
`/approvals` (§10, the public entry) and `/webhook/trigger` (the incident requester) both resolve
through it.

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

// "approval" — a generic approval request created or updated (carries the §10 object + outcome)
{ "type": "approval", "data": { /* §10 + current status/decision */ }}
```

The UI keeps the latest `state` and `incident`, and appends every `log`. The incident's
`status` drives the UI (auto-remediation activity, escalation status, approve/deny buttons).
The `approval` event lets the **approvals dashboard** render pending/decided requests that
aren't incidents (e.g. an external agent's refund request). See [frontend.md](frontend.md).

---

## 8. On-call / ownership registry  *(new in v2; extended for expertise routing in v3)*

`backend/data/on_call.json`. Static schedule **plus area ownership**. Selection logic in
[escalation.md](escalation.md); expertise routing in [triage.md](triage.md).

```json
{
  "engineers": [
    { "id": "eng-01", "name": "Alex",  "slack_id": "U01ALEX", "phone": "+15555550101", "timezone": "America/New_York", "shift_start": "09:00", "shift_end": "21:00", "status": "active", "owns": ["auth-01", "Authentication", "/api/login"] },
    { "id": "eng-02", "name": "Priya", "slack_id": "U02PRIYA","phone": "+15555550102", "timezone": "Asia/Kolkata",      "shift_start": "21:00", "shift_end": "09:00", "status": "active", "owns": ["payment-gw", "Payments", "/api/checkout"] }
  ]
}
```

- **`owns`** *(new in v3)*: areas this engineer owns — service `id`s (§2), service names, route
  prefixes, or module paths. Powers expertise routing: a diagnosed area (§13 `location` /
  `affected_service`) is matched against `owns` to pick the **owning expert**.
- **"awake & available"** = `status == "active"` **and** current local time (per `timezone`)
  falls within `[shift_start, shift_end)` (wrapping past midnight). First match wins; tie-break
  by order. If none match, escalate to the first `active` engineer and log that it's off-hours.
- **Expertise routing (when `EXPERTISE_ROUTING=true`):** prefer the available engineer whose
  `owns` matches the diagnosed area; **fall back** to the awake-&-available rule above when no
  owner matches or the owner is unavailable. Best-effort — see [triage.md](triage.md).

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

## 10. ApprovalRequest — generic inbound  *(new in v3)*

The core v3 object. POSTed to `/approvals` by any caller (an external agent via the SDK, or the
incident pipeline internally). See [approval-api.md](approval-api.md).

```json
{
  "request_id": "apr-3c91",
  "requester": { "...": "§12" },
  "action": "Generate LLMs.txt (GEO agent)",
  "target": null,
  "context": "Prompted to regenerate the site's LLMs.txt for don-drapor",
  "diagnostics": null,
  "risk": null,
  "reversible": true,
  "estimated_tokens": 3500,
  "dangers": [
    "Spends ~3,500 Lyzr credits",
    "Overwrites the existing public/llms.txt",
    "Content is published publicly"
  ],
  "mode": "callback",
  "callback_url": null,
  "wait": "blocking",
  "timeout_sec": 300,
  "approvers": null,
  "created_at": "2026-06-15T09:14:03Z"
}
```

- **`action` / `target`** — what the caller wants to do, and to what. For `mode: callback` the
  action can be any string (CallSign only returns the decision; the caller runs its own action).
- **`context`** — free-text detail to help the human decide.
- **`estimated_tokens`** *(optional, int)* — how many LLM tokens (or credits) this action will
  consume. Shown to the approver so they can weigh cost vs. benefit.
- **`dangers`** *(optional, list[str])* — explicit list of consequences if the action runs.
  Shown verbatim on the approval card.
- **`diagnostics`** *(optional)* — logs / stack trace / deploys for enrichment (see §13b).
- **`risk`** *(optional)* — `low | medium | high`; if absent, enrichment may set it.
- **`mode`** — `gate` (CallSign runs the action via its executor on approval) or `callback`
  (CallSign only returns the decision; the caller runs its own action).
- **`callback_url`** *(optional)* — where CallSign POSTs the §11 outcome in async flows.
- **`wait`** — `blocking` (hold the connection until decided/timeout) or `async` (return
  `request_id` immediately; deliver via callback or polling). See [approval-api.md](approval-api.md).
- **`timeout_sec`** — how long to wait for a human before `decision: timeout`.
- **`approvers`** *(optional routing hint)* — engineer `id`s (§8); otherwise routing picks them
  (expertise routing / on-call, see [escalation.md](escalation.md)).

---

## 11. Decision outcome / callback payload  *(new in v3)*

What the caller receives — returned by the blocking call **and** POSTed to `callback_url`. One shape.

```json
{
  "request_id": "apr-3c91",
  "approved": false,
  "decision": "deny",
  "actor": "eng-02",
  "decided_at": "2026-06-15T09:16:40Z",
  "detail": "Holding rollback; investigating upstream auth first."
}
```

- **`decision`** — `approve | deny | timeout`. **`approved`** — convenience boolean (`decision == approve`).
- **`actor`** — who decided: `<engineer_id>`, `voice`, or `auto` (opt-in auto-approve).
- **`detail`** — optional free text (the human's note, or the timeout reason).

---

## 12. Requester identity  *(new in v3; single-tenant now)*

Who is asking. Single-tenant for the PoC: one shared `APPROVAL_API_KEY` (see [backend.md](backend.md)).

```json
{
  "source": "agent",
  "name": "support-refund-bot",
  "tenant": null
}
```

- **`source`** — `agent | incident | datadog` (the requester channel).
- **`name`** — caller-supplied label, shown to the human.
- **`tenant`** *(FUTURE)* — reserved for multi-tenant. Null while single-tenant; populated once
  per-customer signup + key issuance + per-customer Slack exist (out of scope now).

---

## 13. Diagnosis-from-logs output  *(new in v3)*

What the Diagnostician returns when fed `diagnostics` (§13b) instead of an alert. **Best-guess,
no-codebase** — see the boundary in [triage.md](triage.md).

```json
{
  "error_class": "NullPointer / unhandled exception",
  "location": { "file": "payments/refund.py", "function": "issue_refund", "line": 142 },
  "probable_cause": "Refund path dereferences a null gateway response after deploy dpl_9f2.",
  "suggested_action": "rollback_deployment",
  "confidence": 0.71,
  "summary": "Unhandled exception in issue_refund started right after the last Payments deploy."
}
```

- **`location`** is parsed from the stack trace (which self-describes file/function/line) — the app
  reads it back, it does **not** inspect the repo.
- **`suggested_action`** is a §4b action (gate mode) or a free-text recommendation (callback mode).
- Marked best-guess: location + likely cause, **not** verified code logic or a guaranteed fix.

---

## 13b. Diagnostics input  *(new in v3)*

Optional payload a caller sends inside an ApprovalRequest (§10 `diagnostics`) to get log-based
diagnosis + sharper routing. All fields optional; more in → sharper out.

```json
{
  "logs": "…recent log lines…",
  "stack_trace": "Traceback (most recent call last): …",
  "deploys": [ { "service": "payment-gw", "deploy_id": "dpl_9f2", "deployed_at": "2026-06-15T09:05:00Z" } ]
}
```

- **`stack_trace`** drives `location` in §13. **`deploys`** sharpen "deploy X broke it" correlation.
- Callers should **scrub secrets/PII**; CallSign treats raw logs as short-lived (see [triage.md](triage.md)).

---

## 14. Past-incident memory  *(new in v3 — FUTURE)*

A record of prior resolved requests used to sharpen routing over time ("who fixed this error
before"). Marked FUTURE — not built in the single-tenant PoC.

```json
{
  "error_signature": "issue_refund:NullPointer",
  "resolved_by": "eng-02",
  "action_taken": "rollback_deployment",
  "resolved_at": "2026-05-30T11:02:00Z"
}
```

---

## Field-naming rules

- snake_case everywhere on the wire (Python-friendly; the frontend adapts).
- Server `id` is the only join key — never match on display `name`.
- Timestamps are ISO-8601 UTC strings.
- Enums are closed; an unknown value is a contract violation, not a free-text passthrough.
