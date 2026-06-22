from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Logging — configure once as early as possible, before any other import
# ---------------------------------------------------------------------------
from app.logging_config import configure_logging  # noqa: E402
configure_logging()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
RUNBOOKS_DIR = BASE_DIR / "runbooks"
ON_CALL_PATH = DATA_DIR / "on_call.json"


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key, "")
    if val == "":
        return default
    return val.strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------
APPROVAL_API_KEY: str | None = os.getenv("APPROVAL_API_KEY") or None
ENRICH_REQUESTS: bool = _bool("ENRICH_REQUESTS", True)
EXPERTISE_ROUTING: bool = _bool("EXPERTISE_ROUTING", False)

# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
SLACK_ENABLED: bool = _bool("SLACK_ENABLED", False)
SLACK_INTERACTIVE: bool = _bool("SLACK_INTERACTIVE", False)
SLACK_BOT_TOKEN: str | None = os.getenv("SLACK_BOT_TOKEN") or None
SLACK_SIGNING_SECRET: str | None = os.getenv("SLACK_SIGNING_SECRET") or None

# ---------------------------------------------------------------------------
# Public URL (for Slack callbacks and dashboard links)
# ---------------------------------------------------------------------------
PUBLIC_BACKEND_URL: str | None = os.getenv("PUBLIC_BACKEND_URL") or None
