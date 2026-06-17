"""
Slack integration (slack.md, data-contracts §9).

When SLACK_ENABLED is False (default):
    - Builds the Block Kit card dict.
    - Emits it as a "SLACK" log: "[SLACK] would post: <summary>"
    - Makes NO network call.

When SLACK_ENABLED is True:
    - Uses slack_sdk.WebClient (imported lazily) with SLACK_BOT_TOKEN.
    - Posts to engineer.slack_id (DM) or SLACK_CHANNEL override.

post_incident(engineer, incident, log) -> None
post_thread(incident, text, log) -> None

`log` is log(source: str, message: str).
"""
from __future__ import annotations

import json
from typing import Callable

from app.config import (
    SLACK_ENABLED,
    SLACK_BOT_TOKEN,
    SLACK_INTERACTIVE,
    PUBLIC_BACKEND_URL,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


def _build_card(engineer: dict, incident: dict) -> dict:
    """Build the Block Kit message payload (data-contracts §9)."""
    inc_id = incident.get("incident_id", "unknown")
    diagnosis = incident.get("diagnosis") or {}
    plan = incident.get("plan") or {}

    severity = diagnosis.get("severity", "SEV-?")
    service = diagnosis.get("affected_service", "unknown")
    exact = diagnosis.get("exact_location") or {}
    route = exact.get("route", "")
    deploy_id = exact.get("deploy_id", "")
    commit = exact.get("commit", "")
    summary = diagnosis.get("summary", "")

    steps = plan.get("steps", [])
    proposed = steps[0].get("description", "") if steps else ""

    ui_url = f"{PUBLIC_BACKEND_URL}/incident/{inc_id}" if PUBLIC_BACKEND_URL else f"/incident/{inc_id}"

    header_text = f"🚨 {severity} · {service} ({service})"

    where_parts = []
    if route:
        where_parts.append(f"`{route}`")
    if deploy_id:
        where_parts.append(f"deploy `{deploy_id}`")
    if commit:
        where_parts.append(f"(`{commit}`)")
    where_str = " · ".join(where_parts) if where_parts else "see incident"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Where:* {where_str}\n"
                    f"*What:* {summary}\n"
                ),
            },
        },
    ]

    script = plan.get("script", "")
    if script:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"📞 *{script}*"},
        })
    elif proposed:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Proposed:* {proposed}"},
        })

    actions_elements: list[dict] = [
        {
            "type": "button",
            "style": "primary",
            "text": {"type": "plain_text", "text": "Open CallSign"},
            "url": ui_url,
        }
    ]

    if SLACK_INTERACTIVE:
        actions_elements.append({
            "type": "button",
            "style": "primary",
            "text": {"type": "plain_text", "text": "Approve"},
            "action_id": "approve",
            "value": inc_id,
        })
        actions_elements.append({
            "type": "button",
            "style": "danger",
            "text": {"type": "plain_text", "text": "Deny"},
            "action_id": "deny",
            "value": inc_id,
        })

    blocks.append({"type": "actions", "elements": actions_elements})

    return {
        "channel": engineer.get("slack_id", ""),
        "text": f"🚨 {severity} incident on {service} — approval needed",
        "blocks": blocks,
    }


def post_incident(engineer: dict, incident: dict, log: Callable[[str, str], None]) -> None:
    """Post the incident card (§9) to the engineer's Slack DM.

    When disabled, logs the card summary instead of posting.
    """
    card = _build_card(engineer, incident)
    summary = card.get("text", "incident card")

    if not SLACK_ENABLED:
        log("SLACK", f"[SLACK] would post: {summary}")
        logger.info("[SLACK] disabled — would post card: %s", json.dumps(card, indent=None))
        return

    try:
        import slack_sdk  # noqa: F401 — lazy import so disabled mode needs no dep
        from slack_sdk import WebClient
        client = WebClient(token=SLACK_BOT_TOKEN)
        response = client.chat_postMessage(**card)
        ts = response.get("ts", "")
        log("SLACK", f"Posted incident to @{engineer.get('name')} (ts={ts})")
        logger.info("[SLACK] posted to %s ts=%s", card["channel"], ts)

        # Stash ts for thread replies
        incident["_slack_ts"] = ts
        incident["_slack_channel"] = card["channel"]

    except Exception:
        logger.exception("[SLACK] post_incident failed for incident %s", incident.get("incident_id"))
        log("SLACK", f"[SLACK] post failed — see logs")


def post_thread(incident: dict, text: str, log: Callable[[str, str], None]) -> None:
    """Post a thread reply to the original incident message.

    When disabled, logs the reply text.
    """
    if not SLACK_ENABLED:
        log("SLACK", f"[SLACK] would thread: {text}")
        logger.info("[SLACK] disabled — would post thread: %s", text)
        return

    channel = incident.get("_slack_channel")
    ts = incident.get("_slack_ts")

    if not channel or not ts:
        log("SLACK", "[SLACK] thread skipped — no parent message ts")
        return

    try:
        from slack_sdk import WebClient
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=channel, thread_ts=ts, text=text)
        log("SLACK", f"[SLACK] thread posted: {text}")
        logger.info("[SLACK] thread posted to %s ts=%s", channel, ts)
    except Exception:
        logger.exception("[SLACK] post_thread failed for incident %s", incident.get("incident_id"))
        log("SLACK", f"[SLACK] thread post failed — see logs")
