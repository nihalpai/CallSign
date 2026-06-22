"""
Request enrichment — adds context to an ApprovalRequest dict before routing.

enrich_request(req: dict, log) -> dict
    Mutates the req dict in place and returns it.  Called only when
    ENRICH_REQUESTS is True (the route already guards this; we are defensive
    too).

Enrichment is BEST-EFFORT: any exception is caught, logged, and the
(possibly partial) request is returned so the gate keeps working.

Enrichment NEVER sets decision/approved — a human always decides.
"""
from __future__ import annotations

from typing import Callable

from app.logging_config import get_logger

logger = get_logger(__name__)

# Danger keywords that escalate to "high" risk
_HIGH_RISK_DANGER_KEYWORDS = [
    "irreversible", "overwrite", "delete", "drop", "destroy", "terminate",
    "wipe", "purge", "remove", "truncate",
]

# Large token threshold for risk escalation
_HIGH_TOKEN_THRESHOLD = 10_000

# Keywords from logs/context that suggest elevated risk
_HIGH_RISK_LOG_KEYWORDS = [
    "nullpointer", "null pointer", "outofmemory", "out of memory", "oom",
    "connectionrefused", "connection refused", "payment", "checkout", "auth",
    "permission denied", "forbidden",
]
_MEDIUM_RISK_LOG_KEYWORDS = [
    "timeout", "timed out", "latency", "degraded", "error spike", "5xx",
    "exception", "traceback", "error",
]


def _infer_risk(req: dict) -> str:
    """Derive a risk level from dangers list, estimated_tokens, and log keywords."""
    # dangers list: any mention of irreversible/destructive ops → high
    dangers = req.get("dangers") or []
    danger_text = " ".join(d.lower() for d in dangers)
    if any(kw in danger_text for kw in _HIGH_RISK_DANGER_KEYWORDS):
        return "high"

    # Large token counts suggest a heavy operation → high
    tokens = req.get("estimated_tokens")
    if tokens is not None and tokens >= _HIGH_TOKEN_THRESHOLD:
        return "high"

    # Inspect raw diagnostics / context text
    diag_raw = req.get("diagnostics") or {}
    combined = " ".join([
        str(diag_raw.get("logs") or ""),
        str(diag_raw.get("stack_trace") or ""),
        str(req.get("context") or ""),
        danger_text,
    ]).lower()

    if any(kw in combined for kw in _HIGH_RISK_LOG_KEYWORDS):
        return "high"
    if any(kw in combined for kw in _MEDIUM_RISK_LOG_KEYWORDS):
        return "medium"
    return "low"


def _build_summary(req: dict) -> str:
    action = req.get("action", "unknown action")
    target = req.get("target") or "unknown target"
    risk = req.get("risk", "unknown")
    parts = [f"{action} on {target} — risk: {risk}"]

    dangers = req.get("dangers") or []
    if dangers:
        parts.append(f"dangers: {', '.join(dangers)}")

    tokens = req.get("estimated_tokens")
    if tokens is not None:
        parts.append(f"estimated tokens: {tokens}")

    return ". ".join(p for p in parts if p) + "."


def enrich_request(req: dict, log: Callable[[str, str], None]) -> dict:
    """Enrich an ApprovalRequest dict in place.  Returns the same dict."""
    from app.config import ENRICH_REQUESTS
    if not ENRICH_REQUESTS:
        return req

    try:
        _do_enrich(req, log)
    except Exception:
        logger.exception(
            "enrich_request: unexpected error for %s — enrichment skipped",
            req.get("request_id"),
        )
    return req


def _do_enrich(req: dict, log: Callable[[str, str], None]) -> None:
    """Inner enrichment logic (not guarded — caller handles exceptions)."""
    req_id = req.get("request_id", "<unknown>")

    # Set risk if not already provided by the caller
    if not req.get("risk"):
        req["risk"] = _infer_risk(req)

    # Human-readable summary
    req["enrichment_summary"] = _build_summary(req)

    log("AGENT", f"[ENRICHMENT] {req['enrichment_summary']}")
    logger.info("enrich_request: done for %s (risk=%s)", req_id, req.get("risk"))
