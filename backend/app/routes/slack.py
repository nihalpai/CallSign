"""POST /slack/interactions — optional Slack interactive action handler.

Only active when SLACK_INTERACTIVE=true (disabled by default).
Verifies the Slack request signature, parses the action payload,
maps it to an incident/decision, and delegates to execute_step.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from app.config import SLACK_INTERACTIVE, SLACK_SIGNING_SECRET
from app.events import emit_log, emit_incident
from app.incidents import get_incident, set_decision, set_status, add_attempt
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """Verify the Slack request using the signing secret (HMAC-SHA256)."""
    if not SLACK_SIGNING_SECRET:
        return False
    # Reject requests older than 5 minutes
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
    x_slack_request_timestamp: Annotated[str | None, Header()] = None,
    x_slack_signature: Annotated[str | None, Header()] = None,
) -> dict:
    if not SLACK_INTERACTIVE:
        raise HTTPException(status_code=404, detail="Slack interactions not enabled")

    body = await request.body()

    # Verify signature
    if not _verify_slack_signature(
        body,
        x_slack_request_timestamp or "",
        x_slack_signature or "",
    ):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    # Slack sends application/x-www-form-urlencoded with a "payload" key
    try:
        form_data = urllib.parse.parse_qs(body.decode("utf-8"))
        payload_str = form_data.get("payload", ["{}"])[0]
        payload = json.loads(payload_str)
    except Exception:
        logger.exception("slack_interactions: failed to parse payload")
        raise HTTPException(status_code=400, detail="Invalid payload")

    # Extract action
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id", "")
    incident_id = action.get("value", "")

    if action_id not in ("approve", "deny"):
        return {"ok": True}

    inc = get_incident(incident_id)
    if inc is None:
        logger.warning("slack_interactions: incident %s not found", incident_id)
        return {"ok": True, "warning": f"Incident {incident_id} not found"}

    # Derive actor from the Slack user who clicked
    slack_user = payload.get("user", {})
    actor = slack_user.get("id", "slack-user")

    def log(source: str, message: str) -> None:
        emit_log(source, message)

    # Get the first pending step from the plan
    plan = inc.get("plan") or {}
    steps = plan.get("steps", [])
    pending_step = steps[0] if steps else {}
    action_name = pending_step.get("action", "isolate_container")
    target = pending_step.get("target", inc.get("target", "unknown"))

    if action_id == "approve":
        try:
            from app.remediation.engine import execute_step
            execute_step(inc, action_name, target, actor, log)
        except Exception:
            logger.exception("slack_interactions: execute_step raised for incident %s", incident_id)
    else:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        add_attempt(incident_id, {"action": action_name, "target": target, "actor": actor, "result": "denied", "ts": ts})
        set_decision(incident_id, "deny")
        set_status(incident_id, "failed")
        updated = get_incident(incident_id)
        log("SYSTEM", f"Slack: {actor} denied {action_name} on {target}")
        emit_incident(updated)

    return {"ok": True}
