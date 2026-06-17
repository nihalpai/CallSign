"""
Thin HTTP client for the Lyzr Studio Agent API.

call_agent(agent_id, message, session_id) -> str
    POST {LYZR_API_BASE}/v3/inference/chat/
    Header: x-api-key = LYZR_API_KEY
    Returns the agent's text reply (response["response"]).
    Raises on non-2xx, timeout, or missing response field.
"""
from __future__ import annotations

from app.config import LYZR_API_BASE, LYZR_API_KEY
from app.logging_config import get_logger

logger = get_logger(__name__)

_TIMEOUT = 30.0  # seconds


def call_agent(agent_id: str, message: str, session_id: str) -> str:
    """
    Call a Lyzr Studio agent and return its text reply.

    Raises httpx.HTTPError on non-2xx or network failure.
    Raises KeyError if the response body lacks a "response" field.
    """
    import httpx  # lazy: importing httpx is slow on some filesystems — keep it off the startup path

    url = f"{LYZR_API_BASE}/v3/inference/chat/"
    headers = {
        "x-api-key": LYZR_API_KEY or "",
        "Content-Type": "application/json",
    }
    body = {
        "user_id": "callsign",
        "agent_id": agent_id,
        "session_id": session_id,
        "message": message,
    }

    logger.debug("call_agent → agent=%s session=%s message_len=%d", agent_id, session_id, len(message))

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        reply: str = data["response"]
        logger.debug("call_agent ← agent=%s reply_len=%d", agent_id, len(reply))
        return reply
    except Exception:
        logger.exception("call_agent failed: agent=%s session=%s", agent_id, session_id)
        raise
