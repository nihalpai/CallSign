"""SSE pub/sub fan-out and event shapes (data-contracts §7)."""
from __future__ import annotations

from app import events, state


def test_publish_fans_out_to_all_subscribers():
    q1 = events.subscribe()
    q2 = events.subscribe()

    events.publish({"type": "log", "data": {"x": 1}})

    assert q1.get_nowait() == {"type": "log", "data": {"x": 1}}
    assert q2.get_nowait() == {"type": "log", "data": {"x": 1}}


def test_unsubscribe_stops_delivery():
    q = events.subscribe()
    events.unsubscribe(q)

    events.publish({"type": "log", "data": {}})

    assert q.empty()


def test_emit_log_has_source_message_and_timestamp():
    q = events.subscribe()

    events.emit_log("AGENT", "hello")

    evt = q.get_nowait()
    assert evt["type"] == "log"
    assert evt["data"]["source"] == "AGENT"
    assert evt["data"]["message"] == "hello"
    assert evt["data"]["ts"]  # ISO timestamp present


def test_emit_state_carries_current_servers():
    q = events.subscribe()

    state.set_status("auth-01", "isolated")  # this itself emits a state event

    evt = q.get_nowait()
    assert evt["type"] == "state"
    auth = next(s for s in evt["data"]["servers"] if s["id"] == "auth-01")
    assert auth["status"] == "isolated"
