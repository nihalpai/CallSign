"""SSE pub/sub fan-out and event shapes (data-contracts §7)."""
from __future__ import annotations

from app import events


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
    assert evt["data"]["ts"]


def test_emit_log_system_source():
    q = events.subscribe()

    events.emit_log("SYSTEM", "gate decision made")

    evt = q.get_nowait()
    assert evt["data"]["source"] == "SYSTEM"


def test_emit_approval_carries_request():
    q = events.subscribe()

    req = {"request_id": "apr-test", "status": "approved"}
    events.emit_approval(req)

    evt = q.get_nowait()
    assert evt["type"] == "approval"
    assert evt["data"]["request_id"] == "apr-test"
    assert evt["data"]["status"] == "approved"


def test_multiple_subscribers_all_receive_approval():
    q1 = events.subscribe()
    q2 = events.subscribe()

    req = {"request_id": "apr-multi", "status": "denied"}
    events.emit_approval(req)

    assert q1.get_nowait()["data"]["request_id"] == "apr-multi"
    assert q2.get_nowait()["data"]["request_id"] == "apr-multi"
