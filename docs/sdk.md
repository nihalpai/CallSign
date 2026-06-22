# SDK — how an external agent hooks up

How a developer connects *their* AI agent to CallSign so it pauses for a human before a high-stakes
action. The wire format lives in [approval-api.md](approval-api.md) and [data-contracts.md](data-contracts.md);
this doc is the caller's-eye view.

> The SDK is a thin wrapper around `POST /approvals`. You can skip it and call the HTTP endpoint
> directly — the SDK just makes the common case one line.

---

## The three things a caller needs

1. **An API key** — the shared `APPROVAL_API_KEY` (single-tenant PoC). Sent as `X-API-Key`.
2. **The client** — `pip install callsign` (Python) *or* a plain HTTPS `POST` for any other stack.
3. **One call** — placed right before the risky action, gating it on the human's answer.

---

## Blocking usage (the simplest path)

The caller waits on the open connection until a human decides, then continues. *(Illustrative —
exact SDK names land with the code.)*

```python
from callsign import approve

decision = approve(
    api_key="cs_live_…",
    action="Refund $5,000 to customer 8831",
    context="Customer disputed a duplicate charge; agent confidence 0.72",
    mode="callback",          # the agent will run the refund itself on "yes"
    timeout=300,
)

if decision.approved:
    issue_refund()            # only runs if a human approved
else:
    skip(reason=decision.detail)
```

Under the hood: `POST /approvals` with `wait: "blocking"`; the response is the Decision outcome (§11).

## Async + callback usage (for long waits / fire-and-forget)

The caller fires the request, gets a `request_id`, and is notified later via a `callback_url` POST
(or polls `GET /approvals/{id}`).

```python
req = approve_async(
    api_key="cs_live_…",
    action="Delete 14,000 stale records from analytics_events",
    context="Nightly cleanup job; irreversible",
    mode="callback",
    callback_url="https://my-agent.example.com/callsign/callback",
    timeout=3600,
)
# … your service returns; when a human decides, CallSign POSTs the §11 outcome to callback_url …
```

Use **gate mode** (`mode="gate"`) instead when you want CallSign to *run* the action for you on
approval (a §4b infra action through its executor) rather than running it yourself.

## Sending logs for diagnosis (smart triage)

Pass `diagnostics` (logs / stack trace / recent deploys, §13b) and the request arrives **pre-diagnosed**
(error pinpointed from the trace) and **routed to the area's owner** (§8). CallSign reads the logs you
send — it never needs your codebase. See [triage.md](triage.md).

```python
decision = approve(
    api_key="cs_live_…",
    action="rollback_deployment",
    target="payment-gw",
    mode="gate",
    diagnostics={
        "stack_trace": traceback_text,
        "deploys": recent_deploys,
    },
)
```

The human then sees the pinpointed location, probable cause, and a suggested action on the Slack card.

> **Scrub secrets/PII** from logs before sending — CallSign treats raw logs as short-lived, but the
> caller owns redaction.

---

## Config

| Field | Meaning |
|-------|---------|
| `api_key` | the shared `APPROVAL_API_KEY` (single-tenant) |
| `base_url` | your CallSign backend URL (e.g. the ngrok/public URL) |

## What the human sees

The approver gets a Slack card with the action, the context/blast-radius, any triage output, and
**Approve / Deny** buttons — see [slack.md](slack.md). Whoever responds first resolves the request;
the decision flows back to your agent through the blocking return or the callback.
