"""
Tests for app.escalation — select_engineer and select_approver.

All time injection is done via the `now` parameter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.escalation import select_engineer, select_approver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 16, hour, minute, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# select_engineer — Alex (America/New_York, 09:00-21:00 local)
# ---------------------------------------------------------------------------

class TestSelectEngineerAlexShift:
    """Alex is shift 09:00-21:00 America/New_York (UTC-4 in summer)."""

    def test_selects_alex_during_his_shift(self):
        # 14:00 UTC = 10:00 ET — inside Alex's 09:00-21:00 window
        eng = select_engineer(now=_utc(14, 0))
        assert eng is not None
        assert eng["id"] == "eng-01"
        assert eng["name"] == "Alex"

    def test_selects_alex_at_shift_start(self):
        # 13:00 UTC = 09:00 ET — exactly shift_start (inclusive)
        eng = select_engineer(now=_utc(13, 0))
        assert eng is not None
        assert eng["id"] == "eng-01"


# ---------------------------------------------------------------------------
# select_engineer — Priya (Asia/Kolkata, 21:00-09:00 local) — midnight-wrap
# ---------------------------------------------------------------------------

class TestSelectEngineerPriyaShift:
    """Priya is shift 21:00-09:00 IST (UTC+5:30). Midnight-wrapping window."""

    def test_selects_priya_during_her_shift_late_night(self):
        # 03:00 UTC = 08:30 IST — inside Priya's midnight-wrap [21:00, 09:00)
        # and 03:00 UTC is 23:00 ET previous day — outside Alex's [09:00, 21:00)
        eng = select_engineer(now=_utc(3, 0))
        assert eng is not None
        assert eng["id"] == "eng-02"
        assert eng["name"] == "Priya"

    def test_selects_priya_during_her_shift_morning(self):
        # 02:00 UTC = 07:30 IST — inside Priya's midnight-wrapped window
        eng = select_engineer(now=_utc(2, 0))
        assert eng is not None
        assert eng["id"] == "eng-02"

    def test_priya_not_selected_inside_alex_window(self):
        # 14:00 UTC = 19:30 IST — outside Priya's window; Alex wins
        eng = select_engineer(now=_utc(14, 0))
        assert eng is not None
        assert eng["id"] == "eng-01"


# ---------------------------------------------------------------------------
# select_engineer — fallback
# ---------------------------------------------------------------------------

class TestSelectEngineerFallback:

    def test_fallback_returns_first_active_when_no_shift_match(self):
        import json
        fake_registry = {
            "engineers": [
                {
                    "id": "eng-99",
                    "name": "Nobody",
                    "slack_id": "U99",
                    "phone": "+0",
                    "timezone": "UTC",
                    "shift_start": "00:00",
                    "shift_end": "00:01",
                    "status": "active",
                }
            ]
        }
        with patch("json.load", return_value=fake_registry):
            with patch("builtins.open", side_effect=lambda *a, **k: __import__("io").StringIO(
                json.dumps(fake_registry)
            )):
                eng = select_engineer(now=_utc(12, 30))
        assert eng is not None
        assert eng["id"] == "eng-99"

    def test_no_engineers_returns_none(self):
        import json
        fake_registry = {"engineers": []}
        with patch("json.load", return_value=fake_registry):
            with patch("builtins.open", side_effect=lambda *a, **k: __import__("io").StringIO(
                json.dumps(fake_registry)
            )):
                eng = select_engineer(now=_utc(12, 0))
        assert eng is None


# ---------------------------------------------------------------------------
# select_approver
# ---------------------------------------------------------------------------

class TestSelectApprover:
    _ALEX_HOUR = _utc(14, 0)
    _PRIYA_HOUR = _utc(3, 0)

    def test_no_area_returns_oncall(self):
        eng = select_approver(area=None, now=self._ALEX_HOUR)
        assert eng is not None
        assert eng["id"] == "eng-01"

    def test_expertise_routing_off_ignores_area(self):
        with patch("app.escalation.EXPERTISE_ROUTING", False):
            eng = select_approver(area="payment-gw", now=self._ALEX_HOUR)
        assert eng is not None
        assert eng["id"] == "eng-01"

    def test_expertise_routing_on_routes_to_owner(self):
        with patch("app.escalation.EXPERTISE_ROUTING", True):
            eng = select_approver(area="payment-gw", now=self._PRIYA_HOUR)
        assert eng is not None
        assert eng["id"] == "eng-02"

    def test_expertise_routing_on_falls_back_when_owner_unavailable(self):
        with patch("app.escalation.EXPERTISE_ROUTING", True):
            eng = select_approver(area="payment-gw", now=self._ALEX_HOUR)
        assert eng is not None

    def test_expertise_routing_on_falls_back_for_unknown_area(self):
        with patch("app.escalation.EXPERTISE_ROUTING", True):
            eng = select_approver(area="nonexistent-xyz", now=self._ALEX_HOUR)
        assert eng is not None
        assert eng["id"] == "eng-01"
