# Approval API — the generic front door

The public surface external AI agents call to get a human's yes/no before a high-stakes action.
This is the API companion to [data-contracts.md](data-contracts.md) (which owns the shapes) — it
describes the endpoints and their behavior. The agent-side ergonomics live in [sdk.md](sdk.md).

> **The one idea:** a caller's agent has *already decided* what it wants to do. Before acting, it
> asks CallSign. CallSign (optionally) enriches the request, routes it to a human on Slack, and
> returns the decision. **CallSign never decides the action — a human does.**

---

## `POST /approvals` — create an approval request

Body = an **ApprovalRequest** (§10). Auth via the `X-API-Key` header (see *Auth* below). The
incident pipeline (`/webhook/trigger`) is just one internal caller of this same flow.

Minimal request:
```json
{ "action": "Refund $5,000 to customer 8831", "context": "Disputed duplicate charge", "mode": "callback", "wait": "blocking" }
```

What happens, in order:
1. **(optional) Enrich** — if `ENRICH_REQUESTS=true` (or the caller sent `diagnostics`), the brain
   adds blast radius / risk / a clear human summary, and — for logs — a diagnosis (§13). Enrichment
   only *informs* the human; it never decides. See [triage.md](triage.md), [agents.md](agents.md).
2. **Route** — pick the human: expertise routing to the area owner (§8) when `EXPERTISE_ROUTING=true`,
   else the on-call rule, else the `approvers` hint on the request. See [escalation.md](escalation.md).
3. **Ask** — post the approval card to the chosen human on Slack (and surface it on the dashboard).
4. **Decide** — the human clicks Approve/Deny → `/execute` (§6) → the outcome (§11) is recorded.
5. **Deliver** — return/callback the outcome, and either run the action (gate mode) or hand it back
   (callback mode).

### `wait`: blocking vs async
- **`wait: "blocking"`** — the HTTP response to `POST /approvals` is **held open** until a human
  decides or `timeout_sec` elapses, then returns the **Decision outcome** (§11). Simplest path;
  ideal for demos and short-timeout actions. (Caller should set an HTTP client read-timeout ≥
  `timeout_sec`.)
- **`wait: "async"`** — responds immediately with `{ "request_id": "...", "status": "awaiting_approval" }`.
  The outcome arrives later via a `callback_url` POST (if set) and/or `GET /approvals/{id}` polling.

### `mode`: gate vs callback (what "approve" does)
- **`mode: "gate"`** — on approval CallSign **runs the action itself** through the executor
  (simulate|real). `action` should be a §4b catalog action. This is the v1/v2 behavior. See
  [remediation.md](remediation.md).
- **`mode: "callback"`** — on approval CallSign **runs nothing**; it returns the decision and the
  caller executes its own action. `action` can be any string. This is what lets the gate broker a
  yes/no for actions CallSign has no executor for (refunds, deletes, emails).

Mode and wait are orthogonal — any combination is valid.

### Outcome delivery (§11)
The same outcome shape is returned by the blocking call **and** POSTed to `callback_url`:
```json
{ "request_id": "apr-3c91", "approved": true, "decision": "approve", "actor": "eng-02", "decided_at": "…", "detail": null }
```
- `decision`: `approve | deny | timeout`. On **timeout**, gate mode runs nothing and the action is
  treated as denied; the caller decides what to do next.

---

## `GET /approvals/{id}` — poll status

Returns the current ApprovalRequest (§10) plus its status and, once decided, the outcome (§11).
For `async` callers that don't use a `callback_url`. Returns 404 for an unknown id.

---

## Auth (single-tenant for now)

- One shared **`APPROVAL_API_KEY`** (see [backend.md](backend.md)), sent as `X-API-Key`. Requests
  without a valid key are rejected `401`.
- The request's `requester` identity (§12) is caller-supplied metadata shown to the human
  (`source`, `name`); it is **not** a trust boundary yet.
- **FUTURE (multi-tenant):** per-customer signup, per-customer key issuance, and per-customer Slack
  workspace connection. The `tenant` field (§12) is reserved for it. Out of scope for the PoC.

---

## Relationship to the existing endpoints

| Endpoint | Role |
|----------|------|
| **`POST /approvals`** | the **public entry** — any requester creates an ApprovalRequest (§10) |
| `POST /webhook/trigger` | one specific requester — the **incident vertical** (Datadog/Alert §1 → §10) |
| `POST /execute` | the internal **decision sink** every approval channel hits (§6) — unchanged |
| `GET /stream` | SSE; now also emits `approval` events for non-incident requests (§7) |
| `GET /incident/{id}` | the incident-vertical view of a request (§5) |

`/approvals` and `/webhook/trigger` are two front doors onto the same pipe; `/execute` is the one
back door. Adding the public entry doesn't change the decision sink.
