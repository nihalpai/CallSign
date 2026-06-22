"""
delete_bot.py — fake analytics-cleanup agent demonstrating async + callback mode.

Exercises: POST /approvals, mode=callback, wait=async, callback_url pointing to a
tiny local HTTP listener spun up in a background thread. The bot fires the request,
then blocks waiting for CallSign to POST the outcome to the listener.

Falls back to polling GET /approvals/{id} if a local listener cannot bind (prints
a note explaining which path is active).

Run:
    APPROVAL_API_KEY=cs_test_key python harness/delete_bot.py
"""

import os
import sys
import json
import time
import socket
import threading
import httpx
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_URL = os.environ.get("CALLSIGN_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("APPROVAL_API_KEY", "")
CALLBACK_PORT = int(os.environ.get("CALLBACK_PORT", "9731"))
POLL_INTERVAL = 3       # seconds between polls when callback is unavailable
POLL_TIMEOUT = 360      # seconds before giving up

if not API_KEY:
    print("ERROR: APPROVAL_API_KEY env var is not set.", file=sys.stderr)
    sys.exit(1)


# ── Tiny callback listener ──────────────────────────────────────────────────

_callback_event = threading.Event()
_callback_body: dict = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            _callback_body.update(json.loads(body))
        except json.JSONDecodeError:
            pass
        self.send_response(200)
        self.end_headers()
        _callback_event.set()

    def log_message(self, *args):  # suppress access log noise
        pass


def _start_listener(port: int) -> tuple[HTTPServer | None, str | None]:
    """Start a local callback server. Returns (server, callback_url) or (None, None)."""
    try:
        server = HTTPServer(("0.0.0.0", port), _CallbackHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        # Advertise 127.0.0.1 — CallSign backend is local too.
        return server, f"http://127.0.0.1:{port}/"
    except OSError as exc:
        print(f"[delete_bot] WARNING: could not bind callback listener on :{port} ({exc})")
        return None, None


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[delete_bot] Connecting to {BASE_URL} …")

    server, callback_url = _start_listener(CALLBACK_PORT)
    use_callback = callback_url is not None

    if use_callback:
        print(f"[delete_bot] Callback listener up at {callback_url}")
    else:
        print("[delete_bot] Falling back to polling GET /approvals/{id}")

    payload = {
        "action": "Delete 14,000 stale records from analytics_events",
        "context": "Nightly cleanup job — table is 6 months stale; operation is irreversible.",
        "mode": "callback",
        "wait": "async",
        "timeout_sec": POLL_TIMEOUT,
        "approvers": ["on-call"],
        "requester": {
            "source": "analytics-agent",
            "name": "DeleteBot v1",
        },
    }

    if use_callback:
        payload["callback_url"] = callback_url

    print(f"[delete_bot] Requesting approval: {payload['action']}")

    try:
        response = httpx.post(
            f"{BASE_URL}/approvals",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=30.0,
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

    ack = response.json()
    request_id = ack.get("request_id") or ack.get("id")
    print(f"[delete_bot] Request queued (id={request_id}, status={ack.get('status')})")
    print("[delete_bot] Waiting for a human to decide …")

    if use_callback:
        # Block until CallSign POSTs the outcome to our listener.
        received = _callback_event.wait(timeout=POLL_TIMEOUT)
        if not received:
            print("ERROR: Timed out waiting for callback.", file=sys.stderr)
            sys.exit(1)
        outcome = _callback_body
    else:
        # Poll GET /approvals/{id} until the request is decided.
        outcome = _poll_until_decided(request_id)
        if outcome is None:
            print("ERROR: Timed out polling for decision.", file=sys.stderr)
            sys.exit(1)

    # Print result.
    decision = outcome.get("decision", "unknown")
    actor = outcome.get("actor", "unknown")
    print(f"\n[delete_bot] Decision received")
    print(f"  decision : {decision}")
    print(f"  actor    : {actor}")
    print(f"  detail   : {outcome.get('detail')}")

    if outcome.get("approved"):
        print("\n→ deletion approved — running cleanup (simulated)")
        print("  [DONE] 14,000 rows removed from analytics_events.")
    else:
        print(f"\n→ deletion NOT run — {decision} by {actor}.")

    if server:
        server.shutdown()


def _poll_until_decided(request_id: str) -> dict | None:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        try:
            r = httpx.get(
                f"{BASE_URL}/approvals/{request_id}",
                headers={"X-API-Key": API_KEY},
                timeout=10.0,
            )
            if r.status_code == 200:
                data = r.json()
                status = data.get("status", "")
                if status not in ("awaiting_approval", "pending", ""):
                    # Flatten outcome if nested under "outcome" key.
                    return data.get("outcome") or data
        except httpx.RequestError:
            pass
        time.sleep(POLL_INTERVAL)
    return None


if __name__ == "__main__":
    main()
