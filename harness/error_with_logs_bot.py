"""
error_with_logs_bot.py — fake observability agent demonstrating smart triage.

Exercises: POST /approvals, mode=gate, wait=blocking, diagnostics (stack_trace +
recent deploys). This is the headline path: CallSign reads the logs the caller
sends, pinpoints the error location, routes to the area owner, and the Slack card
arrives pre-diagnosed so the human can decide quickly.

Run:
    APPROVAL_API_KEY=cs_test_key python harness/error_with_logs_bot.py
"""

import os
import sys
import httpx

BASE_URL = os.environ.get("CALLSIGN_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("APPROVAL_API_KEY", "")

if not API_KEY:
    print("ERROR: APPROVAL_API_KEY env var is not set.", file=sys.stderr)
    sys.exit(1)

# Realistic-looking Python stack trace from a payment gateway crash.
# CallSign's Diagnostician will parse this to pinpoint the error location.
STACK_TRACE = """\
Traceback (most recent call last):
  File "/app/workers/checkout_worker.py", line 112, in process_payment
    result = payment_client.charge(customer_id=cid, amount=total)
  File "/app/integrations/payment_gw/client.py", line 78, in charge
    response = self._session.post(self.endpoint, json=payload, timeout=5)
  File "/app/integrations/payment_gw/client.py", line 45, in _request
    raise GatewayTimeout(f"payment-gw did not respond within {self.timeout}s")
app.integrations.payment_gw.client.GatewayTimeout: payment-gw did not respond within 5s

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/app/api/checkout.py", line 55, in post_checkout
    order = checkout_service.submit(cart, customer)
  File "/app/services/checkout_service.py", line 30, in submit
    payment = self._payment.charge(customer.id, cart.total)
  File "/app/services/checkout_service.py", line 38, in _handle_payment_error
    raise CheckoutError("Payment gateway unreachable") from exc
app.services.checkout_service.CheckoutError: Payment gateway unreachable
"""

# Recent deployments — CallSign correlates these with the alert timestamp to
# surface the likely culprit deploy on the Slack card.
RECENT_DEPLOYS = [
    {
        "deploy_id": "dpl_9f2",
        "service": "payment-gw",
        "version": "v2.14.1",
        "deployed_at": "2026-06-18T08:52:00Z",
        "deployed_by": "ci-bot",
        "commit": "a3f7c91",
        "message": "feat: increase connection pool to 50",
    },
    {
        "deploy_id": "dpl_9f1",
        "service": "payment-gw",
        "version": "v2.14.0",
        "deployed_at": "2026-06-17T14:30:00Z",
        "deployed_by": "alice",
        "commit": "d1e4b22",
        "message": "fix: retry on 503",
    },
]

PAYLOAD = {
    "action": "rollback_deployment",
    "target": "payment-gw",
    "context": (
        "5xx error rate on /api/checkout jumped to 40% at 09:14 UTC, "
        "immediately after deploy dpl_9f2. GatewayTimeout in payment_gw client."
    ),
    "mode": "gate",       # CallSign runs the rollback itself (simulated executor).
    "wait": "blocking",   # Hold until human decides.
    "timeout_sec": 300,
    "risk": "high",
    "diagnostics": {
        "stack_trace": STACK_TRACE,
        "deploys": RECENT_DEPLOYS,
    },
    "requester": {
        "source": "observability-agent",
        "name": "ErrorBot v1",
    },
}


def main() -> None:
    print(f"[error_bot] Connecting to {BASE_URL} …")
    print(f"[error_bot] Sending action: {PAYLOAD['action']} on {PAYLOAD['target']}")
    print("[error_bot] Attaching stack trace + deploy history for smart triage …")

    try:
        response = httpx.post(
            f"{BASE_URL}/approvals",
            json=PAYLOAD,
            headers={"X-API-Key": API_KEY},
            timeout=httpx.Timeout(connect=10.0, read=360.0, write=10.0, pool=10.0),
        )
    except httpx.ConnectError:
        print(
            f"ERROR: Could not connect to {BASE_URL}. Is the backend running?",
            file=sys.stderr,
        )
        sys.exit(1)

    if response.status_code == 401:
        print("ERROR: 401 Unauthorized — check APPROVAL_API_KEY.", file=sys.stderr)
        sys.exit(1)

    if response.status_code != 200:
        print(
            f"ERROR: Unexpected response {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    outcome = response.json()
    decision = outcome.get("decision", "unknown")
    actor = outcome.get("actor", "unknown")
    request_id = outcome.get("request_id", "?")

    print(f"\n[error_bot] Decision received (request {request_id})")
    print(f"  decision  : {decision}")
    print(f"  actor     : {actor}")
    print(f"  detail    : {outcome.get('detail')}")

    # In gate mode, CallSign already ran the action (simulated) on approve.
    if outcome.get("approved"):
        print("\n→ rollback approved — CallSign executed (simulated).")
        print("  payment-gw is being rolled back to v2.14.0.")
    else:
        print(f"\n→ rollback NOT executed — {decision} by {actor}.")


if __name__ == "__main__":
    main()
