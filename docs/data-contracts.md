# Data contracts

**Single source of truth for every shape that crosses a boundary.** Change a schema here
first, then update producers/consumers. All examples use the Shellshock demo scenario.

---

## 1. Inbound alert (mock Datadog payload)

POSTed to `/webhook/trigger`. Lives at `backend/data/mock_alerts/shellshock.json`.
We mirror the shape of a real Datadog webhook but only consume a subset.

```json
{
  "alert_id": "dd-2026-0042",
  "title": "Remote code execution attempt detected",
  "alert_type": "security",
  "priority": "P1",
  "tags": ["cve:CVE-2026-1337", "service:auth", "host:auth-01"],
  "body": "Anomalous bash process spawned via CGI on auth-01. Pattern matches Shellshock-class RCE.",
  "host": "auth-01",
  "timestamp": "2026-06-15T09:14:00Z"
}
```

Fields the brain actually relies on: `tags` (carries `cve:`, `service:`, `host:`),
`priority`, `body`, `host`. Everything else is flavor for realism.

---

## 2. Infrastructure state (blast-radius graph)

`backend/data/infrastructure_state.json`. Loaded into memory at startup; mutated in
place. Server `id` is the universal key (alerts, agent output, UI tiles).

```json
{
  "servers": [
    {
      "id": "auth-01",
      "name": "Auth Server",
      "service": "Authentication",
      "status": "healthy",
      "depended_on_by": ["payment-gw", "web-01"],
      "container": "auth-svc-prod"
    },
    {
      "id": "payment-gw",
      "name": "Payment Gateway",
      "service": "Payments",
      "status": "healthy",
      "depended_on_by": ["web-01"],
      "container": "payments-svc-prod"
    },
    {
      "id": "web-01",
      "name": "Web Frontend",
      "service": "Web",
      "status": "healthy",
      "depended_on_by": [],
      "container": "web-svc-prod"
    },
    {
      "id": "db-01",
      "name": "Primary Database",
      "service": "Postgres",
      "status": "healthy",
      "depended_on_by": ["auth-01", "payment-gw"],
      "container": "pg-primary-prod"
    }
  ]
}
```

**Status enum:** `healthy | compromised | isolated`.
**Blast radius** for a server = transitive closure of `depended_on_by` (who breaks if
this server goes down). The Forensic Synthesizer reports it; the UI can highlight it.

---

## 3. Forensic Synthesizer output (Agent 1 → Agent 2)

Agent 1 **must** return strict JSON (no prose). This is the contract Agent 2 and the
backend parse.

```json
{
  "severity": "SEV-1",
  "cve": "CVE-2026-1337",
  "vulnerable_server": "auth-01",
  "service": "Authentication",
  "blast_radius": ["payment-gw", "web-01"],
  "runbook": "CVE-2026-Shellshock-Mitigation.md",
  "recommended_action": "isolate_container",
  "action_target": "auth-01",
  "rationale": "Shellshock-class RCE on the auth container; runbook mandates immediate container isolation to prevent lateral movement to payments."
}
```

- `recommended_action` is a closed enum matching backend-supported actions:
  `isolate_container | revoke_keys | quarantine_host`. (PoC implements
  `isolate_container`; others may be declared but no-op.)
- `action_target` is a server `id` from the infra state.

---

## 4. Commander output (Agent 2 → voice / UI)

Agent 2 returns the spoken script. Plain object, not free text, so the backend can
attach it to the incident.

```json
{
  "script": "Severity one alert: the Auth Server has a Shellshock remote code execution exploit, and Payments depends on it. The runbook calls for immediate container isolation. Do you approve isolating the Auth Server container?",
  "action": "isolate_container",
  "target": "auth-01"
}
```

Hard rule: `script` ≤ 3 sentences, ends in a yes/no question. See [agents.md](agents.md).

---

## 5. Incident object (backend-internal, channel-agnostic)

Created when the brain finishes; resolved when an approval channel reports a decision.

```json
{
  "incident_id": "inc-7f3a",
  "status": "awaiting_approval",          // awaiting_approval | resolved
  "decision": null,                        // null | "approve" | "deny"
  "action": "isolate_container",
  "target": "auth-01",
  "script": "Severity one alert: ...",
  "created_at": "2026-06-15T09:14:03Z"
}
```

---

## 6. `/execute` request (any approval channel → backend)

The one call every tier makes. Tier 0 (button), Tier 1 (Lyzr tool), Tier 2 (phone) all
POST this identical body.

```json
{
  "incident_id": "inc-7f3a",
  "decision": "approve",                   // "approve" | "deny"
  "action": "isolate_container",
  "target": "auth-01"
}
```

On `approve` + `isolate_container`: set `target` server status → `isolated`, emit a
`state` SSE event and a closing `log`. On `deny`: leave status, log the denial.

---

## 7. SSE events (backend → browser)

Stream endpoint `GET /stream`. Each event has a `type` and `data`. The UI switches on
`type`.

```jsonc
// type: "log"  — one terminal line
{ "type": "log", "data": {
    "source": "AGENT",                    // AGENT | SYSTEM | VOICE
    "message": "Cross-referencing CVE-2026-1337 with runbook…",
    "ts": "2026-06-15T09:14:01Z"
}}

// type: "state" — full current infra state (UI re-renders all tiles)
{ "type": "state", "data": { "servers": [ /* shape from §2 */ ] }}

// type: "incident" — incident opened or resolved
{ "type": "incident", "data": { /* shape from §5 */ }}
```

The UI keeps the latest `state` and appends every `log`. An `incident` with
`status: awaiting_approval` shows the Tier-0 approve/deny buttons; `resolved` hides them.

---

## Field-naming rules

- snake_case everywhere on the wire (Python-friendly; the frontend adapts).
- Server `id` is the only join key — never match on display `name`.
- Timestamps are ISO-8601 UTC strings.
