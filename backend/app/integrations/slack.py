"""
Slack integration — generic approval card for the human-in-the-loop gate.

When SLACK_ENABLED is False (default):
    - Builds the Block Kit card dict.
    - Logs it as a "SLACK" log event: "[SLACK] would post: <summary>"
    - Makes NO network call.

When SLACK_ENABLED is True:
    - Uses slack_sdk.WebClient (imported lazily) with SLACK_BOT_TOKEN.
    - Posts to engineer.slack_id (DM).

post_approval(req, approver, log) -> None
    Posts an approval card for an ApprovalRequest.

post_thread(req, text, log) -> None
    Posts a thread reply to an earlier approval card (e.g. resolution update).
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


def _build_approval_card(req: dict, approver: dict) -> dict:
    """Build the Block Kit message payload for an approval request."""
    req_id = req.get("request_id", "unknown")
    action = req.get("action", "unknown action")
    context = req.get("context") or ""
    risk = req.get("risk") or "unknown"
    dangers: list[str] = req.get("dangers") or []
    estimated_tokens: int | None = req.get("estimated_tokens")

    dashboard_url = PUBLIC_BACKEND_URL or "http://localhost:3000"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Approval required: {action}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Context:* {context or '(none)'}\n"
                    f"*Risk:* {risk}"
                ),
            },
        },
    ]

    if dangers:
        danger_lines = "\n".join(f"• {d}" for d in dangers)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Dangers:*\n{danger_lines}"},
        })

    if estimated_tokens is not None:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Estimated Lyzr tokens:* {estimated_tokens:,}"},
        })

    actions_elements: list[dict] = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Open CallSign"},
            "url": dashboard_url,
        },
    ]

    if SLACK_INTERACTIVE:
        actions_elements.insert(0, {
            "type": "button",
            "style": "primary",
            "text": {"type": "plain_text", "text": "Approve"},
            "action_id": "approve",
            "value": req_id,
        })
        actions_elements.insert(1, {
            "type": "button",
            "style": "danger",
            "text": {"type": "plain_text", "text": "Deny"},
            "action_id": "deny",
            "value": req_id,
        })

    blocks.append({"type": "actions", "elements": actions_elements})

    return {
        "channel": approver.get("slack_id", ""),
        "text": f"Approval required: {action} — risk: {risk}",
        "blocks": blocks,
    }


def post_approval(req: dict, approver: dict, log: Callable[[str, str], None]) -> None:
    """Post the approval card to the approver's Slack DM.

    When disabled, logs the card summary instead of posting.
    """
    card = _build_approval_card(req, approver)
    summary = card.get("text", "approval card")

    if not SLACK_ENABLED:
        log("SLACK", f"[SLACK] would post: {summary}")
        logger.info("[SLACK] disabled — would post card: %s", json.dumps(card, indent=None))
        return

    try:
        from slack_sdk import WebClient  # noqa: F401 — lazy import
        client = WebClient(token=SLACK_BOT_TOKEN)
        response = client.chat_postMessage(**card)
        ts = response.get("ts", "")
        log("SLACK", f"Posted approval card to @{approver.get('name')} (ts={ts})")
        logger.info("[SLACK] posted approval card to %s ts=%s", card["channel"], ts)

        # Stash ts for thread replies
        req["_slack_ts"] = ts
        req["_slack_channel"] = card["channel"]

    except Exception:
        logger.exception("[SLACK] post_approval failed for request %s", req.get("request_id"))
        log("SLACK", "[SLACK] post failed — see logs")


def post_thread(req: dict, text: str, log: Callable[[str, str], None]) -> None:
    """Post a thread reply to the original approval message (e.g. resolution update).

    When disabled, logs the text.
    """
    if not SLACK_ENABLED:
        log("SLACK", f"[SLACK] would thread: {text}")
        logger.info("[SLACK] disabled — would post thread: %s", text)
        return

    channel = req.get("_slack_channel")
    ts = req.get("_slack_ts")

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
        logger.exception("[SLACK] post_thread failed for request %s", req.get("request_id"))
        log("SLACK", "[SLACK] thread post failed — see logs")
