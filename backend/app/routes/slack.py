"""POST /slack/interactions — Slack interactive action handler.

Only active when SLACK_INTERACTIVE=true (disabled by default).
Verifies the Slack request signature (HMAC-SHA256), parses the action payload,
maps the button value to an apr-* request_id, and resolves it via the same
path as /execute (resolve + fire waiter + callback + SSE).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from app.config import SLACK_INTERACTIVE, SLACK_SIGNING_SECRET
from app.events import emit_log, emit_approval
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify the Slack request using the signing secret (HMAC-SHA256)."""
    if not SLACK_SIGNING_SECRET:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False

    base_string = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/slack/interactions")
async def slack_interactions(
    request: Request,
    x_slack_request_timestamp: Annotated[Optional[str], Header()] = None,
    x_slack_signature: Annotated[Optional[str], Header()] = None,
) -> dict:
    if not SLACK_INTERACTIVE:
        raise HTTPException(status_code=404, detail="Slack interactions not enabled")

    body = await request.body()

    if not _verify_slack_signature(
        body,
        x_slack_request_timestamp or "",
        x_slack_signature or "",
    ):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    try:
        form_data = urllib.parse.parse_qs(body.decode("utf-8"))
        payload_str = form_data.get("payload", ["{}"])[0]
        payload = json.loads(payload_str)
    except Exception:
        logger.exception("slack_interactions: failed to parse payload")
        raise HTTPException(status_code=400, detail="Invalid payload")

    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id", "")
    request_id = action.get("value", "")

    if action_id not in ("approve", "deny"):
        return {"ok": True}

    from app.requests import get_request, resolve_request
    stored = get_request(request_id)
    if stored is None:
        logger.warning("slack_interactions: request %s not found", request_id)
        return {"ok": True, "warning": f"Request {request_id} not found"}

    _TERMINAL = {"approved", "denied", "returned", "executed", "timed_out"}
    if stored.get("status") in _TERMINAL:
        emit_log("SYSTEM", f"[WARN] Request {request_id} already {stored['status']} — no-op")
        return {"ok": True}

    slack_user = payload.get("user", {})
    actor = slack_user.get("id") or slack_user.get("username") or "slack-user"

    decision = "approve" if action_id == "approve" else "deny"
    stored = resolve_request(request_id, decision, actor)
    if stored is None:
        return {"ok": True, "warning": f"Request {request_id} not found after resolve"}

    emit_log("SYSTEM", f"Slack: {actor} {decision}d request {request_id}")
    emit_approval(stored)

    # Best-effort callback delivery
    callback_url = stored.get("callback_url")
    outcome = stored.get("outcome")
    if callback_url and outcome:
        try:
            import httpx
            resp = httpx.post(callback_url, json=outcome, timeout=10.0)
            logger.info("Slack callback for %s → %s: HTTP %s", request_id, callback_url, resp.status_code)
        except Exception:
            logger.exception("Slack callback delivery failed for %s", request_id)

    # Post thread update
    try:
        from app.integrations.slack import post_thread
        label = "✅ Approved" if decision == "approve" else "❌ Denied"
        post_thread(stored, f"{label} by {actor}", emit_log)
    except Exception:
        logger.exception("post_thread failed for request %s", request_id)

    return {"ok": True}
