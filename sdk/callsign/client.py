from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class CallSignError(Exception):
    """Raised when the CallSign API returns a non-2xx response."""


@dataclass
class Decision:
    """Outcome of a blocking approval request."""

    request_id: str
    approved: bool
    decision: str  # "approve" | "deny" | "timeout"
    actor: Optional[str]
    decided_at: Optional[str]
    detail: Optional[str]

    def __bool__(self) -> bool:
        return self.approved

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "Decision":
        return cls(
            request_id=data["request_id"],
            approved=data["approved"],
            decision=data["decision"],
            actor=data.get("actor"),
            decided_at=data.get("decided_at"),
            detail=data.get("detail"),
        )


class CallSignClient:
    """Thin synchronous client for the CallSign approval gate API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: Optional[float] = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self._api_key, "Content-Type": "application/json"}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise CallSignError(
                f"Authentication failed (401): check your API key. Response: {response.text}"
            )
        if not (200 <= response.status_code < 300):
            raise CallSignError(
                f"CallSign API error {response.status_code}: {response.text}"
            )

    def approve(
        self,
        action: str,
        *,
        target: Optional[str] = None,
        context: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        risk: Optional[str] = None,
        reversible: bool = True,
        mode: str = "callback",
        timeout: int = 300,
        approvers: Optional[List[str]] = None,
        estimated_tokens: Optional[int] = None,
        dangers: Optional[List[str]] = None,
        requester: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """
        Submit a blocking approval request and wait for a human decision.

        The HTTP read timeout is set to timeout_sec + 30 seconds to give the
        server room to return a "timeout" decision before the client times out.
        """
        body: Dict[str, Any] = {
            "action": action,
            "mode": mode,
            "wait": "blocking",
            "timeout_sec": timeout,
            "reversible": reversible,
        }
        if target is not None:
            body["target"] = target
        if context is not None:
            body["context"] = context
        if diagnostics is not None:
            body["diagnostics"] = diagnostics
        if risk is not None:
            body["risk"] = risk
        if approvers is not None:
            body["approvers"] = approvers
        if estimated_tokens is not None:
            body["estimated_tokens"] = estimated_tokens
        if dangers is not None:
            body["dangers"] = dangers
        if requester is not None:
            body["requester"] = requester

        # Give the server 30 s of margin beyond its own timeout to return.
        read_timeout = float(timeout + 30)
        http_timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=10.0, pool=10.0)

        with httpx.Client(timeout=http_timeout) as client:
            response = client.post(
                f"{self._base_url}/approvals",
                json=body,
                headers=self._headers(),
            )

        self._raise_for_status(response)
        return Decision._from_dict(response.json())

    def approve_async(
        self,
        action: str,
        *,
        callback_url: Optional[str] = None,
        target: Optional[str] = None,
        context: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        risk: Optional[str] = None,
        reversible: bool = True,
        mode: str = "callback",
        timeout: int = 300,
        approvers: Optional[List[str]] = None,
        estimated_tokens: Optional[int] = None,
        dangers: Optional[List[str]] = None,
        requester: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Submit a non-blocking approval request. Returns the request_id immediately.
        The outcome is delivered via callback_url POST or GET /approvals/{id} polling.
        """
        body: Dict[str, Any] = {
            "action": action,
            "mode": mode,
            "wait": "async",
            "timeout_sec": timeout,
            "reversible": reversible,
        }
        if callback_url is not None:
            body["callback_url"] = callback_url
        if target is not None:
            body["target"] = target
        if context is not None:
            body["context"] = context
        if diagnostics is not None:
            body["diagnostics"] = diagnostics
        if risk is not None:
            body["risk"] = risk
        if approvers is not None:
            body["approvers"] = approvers
        if estimated_tokens is not None:
            body["estimated_tokens"] = estimated_tokens
        if dangers is not None:
            body["dangers"] = dangers
        if requester is not None:
            body["requester"] = requester

        client_timeout = self._default_timeout or 30.0
        with httpx.Client(timeout=client_timeout) as client:
            response = client.post(
                f"{self._base_url}/approvals",
                json=body,
                headers=self._headers(),
            )

        self._raise_for_status(response)
        return response.json()["request_id"]

    def get_request(self, request_id: str) -> Dict[str, Any]:
        """Fetch the current status and outcome of an approval request."""
        client_timeout = self._default_timeout or 30.0
        with httpx.Client(timeout=client_timeout) as client:
            response = client.get(
                f"{self._base_url}/approvals/{request_id}",
                headers=self._headers(),
            )
        self._raise_for_status(response)
        return response.json()
