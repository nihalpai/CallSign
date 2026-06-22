"""
X-API-Key authentication dependency for POST /approvals.

Single-tenant: one shared APPROVAL_API_KEY.
When the key is unset, auth is open (disabled) and a one-time warning is emitted.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from app.config import APPROVAL_API_KEY
from app.logging_config import get_logger

logger = get_logger(__name__)

_warned_open: bool = False


async def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    global _warned_open

    if not APPROVAL_API_KEY:
        if not _warned_open:
            logger.warning("APPROVAL_API_KEY unset — /approvals auth is OPEN")
            _warned_open = True
        return

    if x_api_key != APPROVAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
