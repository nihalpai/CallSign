from __future__ import annotations
import asyncio
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from app.events import subscribe, unsubscribe

router = APIRouter()


async def event_stream():
    q = subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30)
                yield {"event": event["type"], "data": json.dumps(event["data"])}
            except asyncio.TimeoutError:
                yield {"comment": "keep-alive"}
    except asyncio.CancelledError:
        pass
    finally:
        unsubscribe(q)


@router.get("/stream")
async def stream():
    return EventSourceResponse(event_stream())
