# callsign

Python client SDK for the [CallSign](https://github.com/lyzr/callsign) human-in-the-loop approval gate.

Before a risky action, your AI agent asks CallSign. A human approves or denies it on Slack (or the dashboard). Your agent only proceeds on "yes."

## Install

```bash
pip install -e sdk/     # from the repo root
# or, once published:
pip install callsign
```

## Quickstart

### Blocking (simplest path)

The call blocks until a human decides, then your code continues:

```python
from callsign import approve

decision = approve(
    api_key="cs_live_…",
    base_url="https://your-callsign-host",
    action="Refund $5,000 to customer 8831",
    context="Customer disputed a duplicate charge; agent confidence 0.72",
    mode="callback",   # you run the action yourself on "yes"
    timeout=300,
)

if decision:           # decision.__bool__() == decision.approved
    issue_refund()
else:
    skip(reason=decision.detail)
```

### Async + callback (fire and forget)

Fires the request immediately and returns a `request_id`. The outcome arrives via a `callback_url` POST, or you can poll with `get_request()`:

```python
from callsign import approve_async, get_request

req_id = approve_async(
    api_key="cs_live_…",
    base_url="https://your-callsign-host",
    action="Delete 14,000 stale records from analytics_events",
    context="Nightly cleanup job; irreversible",
    mode="callback",
    callback_url="https://my-agent.example.com/callsign/callback",
    timeout=3600,
)

# … your service returns; when a human decides, CallSign POSTs the outcome …

# Or poll manually:
status = get_request(req_id, api_key="cs_live_…", base_url="…")
print(status["status"])   # "awaiting_approval" | "approved" | "denied"
```

### Passing dangers and estimated token cost

Use `dangers` to show the approver exactly what will happen, and `estimated_tokens` to surface
the credit cost.  Both are shown on the approval card.

```python
from callsign import approve

decision = approve(
    api_key="cs_live_…",
    base_url="https://your-callsign-host",
    action="Generate LLMs.txt (GEO agent)",
    context="Prompted to regenerate the site's LLMs.txt for don-drapor",
    estimated_tokens=3500,
    dangers=[
        "Spends ~3,500 Lyzr credits",
        "Overwrites the existing public/llms.txt",
        "Content is published publicly",
    ],
    mode="callback",       # you run the action yourself on approval
    requester={"source": "agent", "name": "geo-agent"},
)

if decision:
    generate_llms_txt_with_lyzr()   # only reached on Approve
else:
    print("Denied — skipped, credits saved.")
```

### Sending logs for diagnosis

Pass `diagnostics` to let CallSign pinpoint errors in your logs and route to the right area owner:

```python
from callsign import approve

decision = approve(
    api_key="cs_live_…",
    base_url="https://your-callsign-host",
    action="rollback_deployment",
    target="payment-gw",
    mode="gate",          # CallSign runs the action itself on approval
    diagnostics={
        "stack_trace": traceback_text,
        "deploys": recent_deploys,
    },
)
```

Scrub secrets and PII from logs before sending — CallSign treats raw logs as short-lived, but the caller owns redaction.

## Using the client class directly

```python
from callsign import CallSignClient

client = CallSignClient(api_key="cs_live_…", base_url="https://your-callsign-host")

# Blocking
decision = client.approve("drop production table", risk="high", reversible=False)

# Async
req_id = client.approve_async("send bulk email", callback_url="https://…/cb")

# Poll
req = client.get_request(req_id)
```

## Config

| Parameter | Description |
|-----------|-------------|
| `api_key` | The shared `APPROVAL_API_KEY` (single-tenant PoC) |
| `base_url` | Your CallSign backend URL (e.g. the ngrok or public URL) |

## Error handling

All non-2xx responses raise `CallSignError` with the HTTP status and body. On 401 the message calls out the API key explicitly.

```python
from callsign import approve, CallSignError

try:
    decision = approve("risky action", api_key="bad_key", base_url="…")
except CallSignError as e:
    print(e)   # "Authentication failed (401): check your API key. Response: …"
```
