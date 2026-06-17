"""
Tests for app.integrations.datadog.map_datadog_payload.

Covers: realistic Datadog body, tag parsing, priority defaulting,
host fallback, timestamp normalization, missing-field tolerance.
"""
from __future__ import annotations

import pytest
from app.integrations.datadog import map_datadog_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _realistic_raw() -> dict:
    """A realistic Datadog webhook body using the §1b template vars as values."""
    return {
        "alert_id": "dd-2026-0042",
        "title": "5xx error rate spike on checkout",
        "alert_type": "reliability",
        "priority": "P1",
        "tags": "service:payment-gw,host:payment-gw,route:/api/checkout,deploy:dpl_9f2",
        "body": "HTTP 5xx on /api/checkout jumped to 40% immediately after deploy dpl_9f2.",
        "host": "payment-gw",
        "timestamp": "2026-06-15T09:14:00Z",
    }


# ---------------------------------------------------------------------------
# Happy-path mapping
# ---------------------------------------------------------------------------

class TestMapDatadogPayloadHappyPath:

    def test_alert_id_mapped(self):
        alert = map_datadog_payload(_realistic_raw())
        assert alert["alert_id"] == "dd-2026-0042"

    def test_title_mapped(self):
        alert = map_datadog_payload(_realistic_raw())
        assert alert["title"] == "5xx error rate spike on checkout"

    def test_alert_type_always_reliability(self):
        alert = map_datadog_payload(_realistic_raw())
        assert alert["alert_type"] == "reliability"

    def test_priority_p1_preserved(self):
        alert = map_datadog_payload(_realistic_raw())
        assert alert["priority"] == "P1"

    def test_body_mapped(self):
        alert = map_datadog_payload(_realistic_raw())
        assert "40%" in alert["body"]

    def test_host_mapped(self):
        alert = map_datadog_payload(_realistic_raw())
        assert alert["host"] == "payment-gw"

    def test_timestamp_iso(self):
        alert = map_datadog_payload(_realistic_raw())
        ts = alert["timestamp"]
        assert ts == "2026-06-15T09:14:00Z"

    def test_internal_alert_has_required_fields(self):
        alert = map_datadog_payload(_realistic_raw())
        required = {"alert_id", "title", "alert_type", "priority", "tags", "body", "host", "timestamp"}
        assert required.issubset(set(alert.keys()))


# ---------------------------------------------------------------------------
# Tag parsing
# ---------------------------------------------------------------------------

class TestTagParsing:

    def test_comma_string_split_into_list(self):
        raw = _realistic_raw()
        raw["tags"] = "service:payment-gw,host:payment-gw,route:/api/checkout,deploy:dpl_9f2"
        alert = map_datadog_payload(raw)
        assert isinstance(alert["tags"], list)
        assert len(alert["tags"]) == 4

    def test_tags_with_spaces_stripped(self):
        raw = _realistic_raw()
        raw["tags"] = " service:payment-gw , host:payment-gw "
        alert = map_datadog_payload(raw)
        assert alert["tags"] == ["service:payment-gw", "host:payment-gw"]

    def test_list_tags_passed_through(self):
        raw = _realistic_raw()
        raw["tags"] = ["service:payment-gw", "host:payment-gw"]
        alert = map_datadog_payload(raw)
        assert alert["tags"] == ["service:payment-gw", "host:payment-gw"]

    def test_service_tag_readable(self):
        raw = _realistic_raw()
        alert = map_datadog_payload(raw)
        service_tags = [t for t in alert["tags"] if t.startswith("service:")]
        assert service_tags == ["service:payment-gw"]

    def test_deploy_tag_readable(self):
        raw = _realistic_raw()
        alert = map_datadog_payload(raw)
        deploy_tags = [t for t in alert["tags"] if t.startswith("deploy:")]
        assert deploy_tags == ["deploy:dpl_9f2"]


# ---------------------------------------------------------------------------
# Priority defaulting
# ---------------------------------------------------------------------------

class TestPriorityDefaulting:

    def test_missing_priority_defaults_to_p3(self):
        raw = _realistic_raw()
        del raw["priority"]
        alert = map_datadog_payload(raw)
        assert alert["priority"] == "P3"

    def test_empty_priority_defaults_to_p3(self):
        raw = _realistic_raw()
        raw["priority"] = ""
        alert = map_datadog_payload(raw)
        assert alert["priority"] == "P3"

    def test_invalid_priority_defaults_to_p3(self):
        raw = _realistic_raw()
        raw["priority"] = "critical"
        alert = map_datadog_payload(raw)
        assert alert["priority"] == "P3"

    def test_p5_preserved(self):
        raw = _realistic_raw()
        raw["priority"] = "P5"
        alert = map_datadog_payload(raw)
        assert alert["priority"] == "P5"


# ---------------------------------------------------------------------------
# Host fallback
# ---------------------------------------------------------------------------

class TestHostFallback:

    def test_host_from_tag_when_hostname_blank(self):
        raw = _realistic_raw()
        raw["host"] = ""
        raw["tags"] = "service:payment-gw,host:payment-gw"
        alert = map_datadog_payload(raw)
        # Falls back to host: tag
        assert alert["host"] == "payment-gw"

    def test_host_from_service_tag_when_no_host_tag(self):
        raw = _realistic_raw()
        raw["host"] = ""
        raw["tags"] = "service:checkout-svc"
        alert = map_datadog_payload(raw)
        assert alert["host"] == "checkout-svc"

    def test_host_unknown_when_no_fallback(self):
        raw = _realistic_raw()
        raw["host"] = ""
        raw["tags"] = "env:prod"
        alert = map_datadog_payload(raw)
        assert alert["host"] == "unknown"


# ---------------------------------------------------------------------------
# Timestamp normalization
# ---------------------------------------------------------------------------

class TestTimestampNormalization:

    def test_iso_utc_string_preserved(self):
        raw = _realistic_raw()
        raw["timestamp"] = "2026-06-15T09:14:00Z"
        alert = map_datadog_payload(raw)
        assert alert["timestamp"] == "2026-06-15T09:14:00Z"

    def test_epoch_ms_as_string_converted(self):
        raw = _realistic_raw()
        # 2026-06-15T09:14:00Z in ms
        raw["timestamp"] = "1750000440000"
        alert = map_datadog_payload(raw)
        assert alert["timestamp"].endswith("Z")
        assert "T" in alert["timestamp"]

    def test_missing_timestamp_returns_current(self):
        raw = _realistic_raw()
        del raw["timestamp"]
        alert = map_datadog_payload(raw)
        ts = alert["timestamp"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_unparseable_timestamp_returns_current(self):
        raw = _realistic_raw()
        raw["timestamp"] = "not-a-date"
        alert = map_datadog_payload(raw)
        ts = alert["timestamp"]
        assert ts.endswith("Z")


# ---------------------------------------------------------------------------
# Missing-field tolerance
# ---------------------------------------------------------------------------

class TestMissingFieldTolerance:

    def test_completely_empty_payload(self):
        alert = map_datadog_payload({})
        assert alert["alert_id"] == ""
        assert alert["title"] == ""
        assert alert["alert_type"] == "reliability"
        assert alert["priority"] == "P3"
        assert alert["tags"] == []
        assert alert["body"] == ""
        assert alert["host"] == "unknown"
        assert alert["timestamp"].endswith("Z")

    def test_extra_fields_ignored(self):
        raw = _realistic_raw()
        raw["datadog_internal_thing"] = "should not appear"
        raw["__event_id"] = 99999
        alert = map_datadog_payload(raw)
        assert "datadog_internal_thing" not in alert
        assert "__event_id" not in alert

    def test_partial_payload_does_not_raise(self):
        partial = {
            "alert_id": "dd-partial",
            "title": "Partial alert",
        }
        alert = map_datadog_payload(partial)
        assert alert["alert_id"] == "dd-partial"
        assert alert["priority"] == "P3"
