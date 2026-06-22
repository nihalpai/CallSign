from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import CallSignClient, CallSignError, Decision

__all__ = [
    "approve",
    "approve_async",
    "get_request",
    "Decision",
    "CallSignClient",
    "CallSignError",
]


def approve(
    action: str,
    *,
    api_key: str,
    base_url: str,
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
    Module-level convenience: create a client and submit a blocking approval.

    Example::

        from callsign import approve

        decision = approve(
            api_key="cs_live_…",
            base_url="https://callsign.example.com",
            action="Refund $5,000 to customer 8831",
            context="Customer disputed a duplicate charge",
            mode="callback",
            timeout=300,
        )
        if decision:
            issue_refund()
    """
    client = CallSignClient(api_key=api_key, base_url=base_url)
    return client.approve(
        action,
        target=target,
        context=context,
        diagnostics=diagnostics,
        risk=risk,
        reversible=reversible,
        mode=mode,
        timeout=timeout,
        approvers=approvers,
        estimated_tokens=estimated_tokens,
        dangers=dangers,
        requester=requester,
    )


def approve_async(
    action: str,
    *,
    api_key: str,
    base_url: str,
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
    Module-level convenience: create a client and submit a non-blocking approval.
    Returns the request_id immediately.

    Example::

        from callsign import approve_async

        req_id = approve_async(
            api_key="cs_live_…",
            base_url="https://callsign.example.com",
            action="Delete 14,000 stale records from analytics_events",
            callback_url="https://my-agent.example.com/callsign/callback",
            mode="callback",
        )
    """
    client = CallSignClient(api_key=api_key, base_url=base_url)
    return client.approve_async(
        action,
        callback_url=callback_url,
        target=target,
        context=context,
        diagnostics=diagnostics,
        risk=risk,
        reversible=reversible,
        mode=mode,
        timeout=timeout,
        approvers=approvers,
        estimated_tokens=estimated_tokens,
        dangers=dangers,
        requester=requester,
    )


def get_request(
    request_id: str,
    *,
    api_key: str,
    base_url: str,
) -> Dict[str, Any]:
    """
    Module-level convenience: fetch the current status of an approval request.

    Example::

        from callsign import get_request

        req = get_request(request_id="apr-3c91", api_key="cs_live_…", base_url="…")
        print(req["status"])
    """
    client = CallSignClient(api_key=api_key, base_url=base_url)
    return client.get_request(request_id)
