from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

# Set of subscriber queues — one per connected SSE client
_subscribers: set[asyncio.Queue] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def publish(event: dict[str, Any]) -> None:
    for q in _subscribers:
        q.put_nowait(event)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def emit_log(source: str, message: str) -> None:
    publish({"type": "log", "data": {"source": source, "message": message, "ts": _now_iso()}})


def emit_approval(req: dict[str, Any]) -> None:
    publish({"type": "approval", "data": req})
