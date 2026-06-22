"""
refund_bot.py — fake support agent demonstrating the simplest gate path.

Exercises: POST /approvals, mode=callback, wait=blocking, no diagnostics.
The bot asks CallSign to approve "Refund $5,000 to customer 8831", blocks until
a human decides, then (on approve) prints a simulated refund confirmation.

Run:
    APPROVAL_API_KEY=cs_test_key python harness/refund_bot.py
"""

import os
import sys
import httpx

BASE_URL = os.environ.get("CALLSIGN_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("APPROVAL_API_KEY", "")

if not API_KEY:
    print("ERROR: APPROVAL_API_KEY env var is not set.", file=sys.stderr)
    sys.exit(1)

PAYLOAD = {
    "action": "Refund $5,000 to customer 8831",
    "context": "Customer disputed a duplicate charge; agent confidence 0.72.",
    "mode": "callback",   # CallSign returns the decision; we execute the refund ourselves.
    "wait": "blocking",   # Hold the connection open until a human decides.
    "timeout_sec": 300,
    "approvers": ["on-call"],
    "requester": {
        "source": "support-agent",
        "name": "RefundBot v1",
    },
}

def main() -> None:
    print(f"[refund_bot] Connecting to {BASE_URL} …")
    print(f"[refund_bot] Requesting approval: {PAYLOAD['action']}")

    try:
        # Use a read-timeout that comfortably exceeds timeout_sec so the connection
        # is not killed by the HTTP client before the human responds.
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

    print(f"\n[refund_bot] Decision received (request {request_id})")
    print(f"  decision : {decision}")
    print(f"  actor    : {actor}")
    print(f"  detail   : {outcome.get('detail')}")

    if outcome.get("approved"):
        print("\n→ issuing refund (simulated)")
        print("  [DONE] $5,000 credited to customer 8831.")
    else:
        print(f"\n→ refund NOT issued — {decision} by {actor}.")


if __name__ == "__main__":
    main()
