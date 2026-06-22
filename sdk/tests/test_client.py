from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import httpx
import pytest

from callsign import CallSignClient, CallSignError, Decision, approve, approve_async, get_request

BASE_URL = "http://callsign.test"
API_KEY = "cs_test_key"

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

APPROVE_OUTCOME: Dict[str, Any] = {
    "request_id": "apr-abc1",
    "approved": True,
    "decision": "approve",
    "actor": "eng-01",
    "decided_at": "2026-01-01T12:00:00Z",
    "detail": None,
}

DENY_OUTCOME: Dict[str, Any] = {
    "request_id": "apr-abc2",
    "approved": False,
    "decision": "deny",
    "actor": "eng-02",
    "decided_at": "2026-01-01T12:01:00Z",
    "detail": "Risk too high",
}

ASYNC_RESPONSE: Dict[str, Any] = {
    "request_id": "apr-xyz9",
    "status": "awaiting_approval",
}

GET_RESPONSE: Dict[str, Any] = {
    "request_id": "apr-abc1",
    "status": "approved",
    "action": "rollback_deployment",
    "outcome": APPROVE_OUTCOME,
}


def _mock_http_client(status: int, body: Dict[str, Any]) -> MagicMock:
    """
    Return a MagicMock that behaves like httpx.Client used as a context manager
    and returns the given status/body for any request method.
    """
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.text = json.dumps(body)
    response.json.return_value = body

    inner = MagicMock()
    inner.post.return_value = response
    inner.get.return_value = response

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=inner)
    ctx.__exit__ = MagicMock(return_value=False)

    mock_class = MagicMock(return_value=ctx)
    return mock_class, inner, response


# ---------------------------------------------------------------------------
# Decision dataclass
# ---------------------------------------------------------------------------

class TestDecision:
    def test_approved_truthy(self) -> None:
        d = Decision._from_dict(APPROVE_OUTCOME)
        assert bool(d) is True
        assert d.approved is True
        assert d.decision == "approve"
        assert d.actor == "eng-01"
        assert d.request_id == "apr-abc1"
        assert d.detail is None

    def test_denied_falsy(self) -> None:
        d = Decision._from_dict(DENY_OUTCOME)
        assert bool(d) is False
        assert d.approved is False
        assert d.detail == "Risk too high"


# ---------------------------------------------------------------------------
# CallSignClient.approve (blocking)
# ---------------------------------------------------------------------------

class TestApproveBlocking:
    def test_request_body_and_headers(self) -> None:
        """POST must send correct body fields and X-API-Key header."""
        mock_class, inner, _ = _mock_http_client(200, APPROVE_OUTCOME)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            decision = client.approve(
                "Refund $5,000",
                context="Disputed charge",
                mode="callback",
                timeout=120,
                reversible=True,
            )

        call_args = inner.post.call_args
        url = call_args[0][0]
        kwargs = call_args[1]

        assert url == f"{BASE_URL}/approvals"
        assert kwargs["headers"]["X-API-Key"] == API_KEY

        body = kwargs["json"]
        assert body["action"] == "Refund $5,000"
        assert body["wait"] == "blocking"
        assert body["mode"] == "callback"
        assert body["timeout_sec"] == 120
        assert body["context"] == "Disputed charge"
        assert body["reversible"] is True

        assert isinstance(decision, Decision)
        assert decision.approved is True

    def test_returns_decision_on_approve(self) -> None:
        mock_class, inner, _ = _mock_http_client(200, APPROVE_OUTCOME)
        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            d = client.approve("do something")
        assert isinstance(d, Decision)
        assert d.approved is True
        assert d.request_id == "apr-abc1"

    def test_deny_decision_is_falsy(self) -> None:
        mock_class, inner, _ = _mock_http_client(200, DENY_OUTCOME)
        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            d = client.approve("do something risky")
        assert not d
        assert d.decision == "deny"
        assert d.detail == "Risk too high"

    def test_diagnostics_forwarded(self) -> None:
        """diagnostics dict must appear verbatim in the POST body."""
        mock_class, inner, _ = _mock_http_client(200, APPROVE_OUTCOME)
        diag = {"stack_trace": "Traceback ...", "deploys": [{"version": "1.2"}]}

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            client.approve("rollback_deployment", diagnostics=diag)

        body = inner.post.call_args[1]["json"]
        assert body["diagnostics"] == diag

    def test_optional_fields_omitted_when_none(self) -> None:
        """target/context/diagnostics/risk/approvers/estimated_tokens/dangers must not appear in body when not set."""
        mock_class, inner, _ = _mock_http_client(200, APPROVE_OUTCOME)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            client.approve("minimal action")

        body = inner.post.call_args[1]["json"]
        for field in ("target", "context", "diagnostics", "risk", "approvers", "estimated_tokens", "dangers"):
            assert field not in body, f"Unexpected field in body: {field}"

    def test_estimated_tokens_and_dangers_sent(self) -> None:
        """estimated_tokens and dangers must appear verbatim in the POST body when set."""
        mock_class, inner, _ = _mock_http_client(200, APPROVE_OUTCOME)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            client.approve(
                "Generate LLMs.txt (GEO agent)",
                estimated_tokens=3500,
                dangers=["Spends ~3,500 Lyzr credits", "Overwrites public/llms.txt"],
            )

        body = inner.post.call_args[1]["json"]
        assert body["estimated_tokens"] == 3500
        assert body["dangers"] == ["Spends ~3,500 Lyzr credits", "Overwrites public/llms.txt"]

    def test_http_timeout_has_margin(self) -> None:
        """httpx.Client must be constructed with a read timeout > timeout_sec."""
        mock_class, _, _ = _mock_http_client(200, APPROVE_OUTCOME)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            client.approve("action", timeout=100)

        timeout_arg = mock_class.call_args[1]["timeout"]
        # httpx.Timeout object — read value must be >= 100 + some margin
        assert timeout_arg.read >= 130  # 100 + 30


# ---------------------------------------------------------------------------
# CallSignClient.approve_async
# ---------------------------------------------------------------------------

class TestApproveAsync:
    def test_body_uses_async_wait(self) -> None:
        mock_class, inner, _ = _mock_http_client(200, ASYNC_RESPONSE)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            req_id = client.approve_async(
                "Delete 14,000 records",
                callback_url="https://agent.example.com/cb",
            )

        body = inner.post.call_args[1]["json"]
        assert body["wait"] == "async"
        assert body["callback_url"] == "https://agent.example.com/cb"
        assert req_id == "apr-xyz9"

    def test_api_key_header_present(self) -> None:
        mock_class, inner, _ = _mock_http_client(200, ASYNC_RESPONSE)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            client.approve_async("some action")

        headers = inner.post.call_args[1]["headers"]
        assert headers["X-API-Key"] == API_KEY

    def test_returns_request_id_string(self) -> None:
        mock_class, _, _ = _mock_http_client(200, ASYNC_RESPONSE)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            result = client.approve_async("some action")

        assert isinstance(result, str)
        assert result == "apr-xyz9"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_401_raises_with_api_key_hint(self) -> None:
        mock_class, _, response = _mock_http_client(401, {})
        response.text = "Unauthorized"

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key="bad_key", base_url=BASE_URL)
            with pytest.raises(CallSignError) as exc_info:
                client.approve("do something")

        msg = str(exc_info.value)
        assert "401" in msg
        assert "API key" in msg

    def test_500_raises_callsign_error(self) -> None:
        mock_class, _, response = _mock_http_client(500, {})
        response.text = "Internal Server Error"

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            with pytest.raises(CallSignError) as exc_info:
                client.approve("do something")

        assert "500" in str(exc_info.value)

    def test_404_on_get_request_raises(self) -> None:
        mock_class, _, response = _mock_http_client(404, {})
        response.text = "Not Found"

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            with pytest.raises(CallSignError):
                client.get_request("apr-unknown")


# ---------------------------------------------------------------------------
# get_request
# ---------------------------------------------------------------------------

class TestGetRequest:
    def test_returns_dict_with_status(self) -> None:
        mock_class, _, _ = _mock_http_client(200, GET_RESPONSE)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            result = client.get_request("apr-abc1")

        assert result["request_id"] == "apr-abc1"
        assert result["status"] == "approved"

    def test_correct_url(self) -> None:
        mock_class, inner, _ = _mock_http_client(200, GET_RESPONSE)

        with patch("callsign.client.httpx.Client", mock_class):
            client = CallSignClient(api_key=API_KEY, base_url=BASE_URL)
            client.get_request("apr-abc1")

        url = inner.get.call_args[0][0]
        assert url == f"{BASE_URL}/approvals/apr-abc1"


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

class TestModuleFunctions:
    def test_approve_module_fn_returns_decision(self) -> None:
        mock_class, _, _ = _mock_http_client(200, APPROVE_OUTCOME)

        with patch("callsign.client.httpx.Client", mock_class):
            d = approve("do something", api_key=API_KEY, base_url=BASE_URL)

        assert isinstance(d, Decision)
        assert d.approved is True

    def test_approve_async_module_fn_returns_request_id(self) -> None:
        mock_class, _, _ = _mock_http_client(200, ASYNC_RESPONSE)

        with patch("callsign.client.httpx.Client", mock_class):
            req_id = approve_async("delete records", api_key=API_KEY, base_url=BASE_URL)

        assert req_id == "apr-xyz9"

    def test_get_request_module_fn(self) -> None:
        mock_class, _, _ = _mock_http_client(200, GET_RESPONSE)

        with patch("callsign.client.httpx.Client", mock_class):
            result = get_request("apr-abc1", api_key=API_KEY, base_url=BASE_URL)

        assert result["status"] == "approved"
