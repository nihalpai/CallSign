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
INFRA_STATE_PATH = DATA_DIR / "infrastructure_state.json"
DEPLOYMENTS_PATH = DATA_DIR / "deployments.json"
ON_CALL_PATH = DATA_DIR / "on_call.json"
MOCK_ALERTS_DIR = DATA_DIR / "mock_alerts"


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key, "")
    if val == "":
        return default
    return val.strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Lyzr
# ---------------------------------------------------------------------------
LYZR_API_KEY: str | None = os.getenv("LYZR_API_KEY") or None
LYZR_API_BASE: str = os.getenv("LYZR_API_BASE", "https://agent-prod.studio.lyzr.ai")
LYZR_DIAGNOSTICIAN_AGENT_ID: str | None = os.getenv("LYZR_DIAGNOSTICIAN_AGENT_ID") or None
LYZR_STRATEGIST_AGENT_ID: str | None = os.getenv("LYZR_STRATEGIST_AGENT_ID") or None
LYZR_VOICE_AGENT_ID: str | None = os.getenv("LYZR_VOICE_AGENT_ID") or None

# ---------------------------------------------------------------------------
# Execution + autonomy
# ---------------------------------------------------------------------------
EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "simulate")
AUTO_REMEDIATE: bool = _bool("AUTO_REMEDIATE", True)
AUTO_REMEDIATE_MAX_SEVERITY: str = os.getenv("AUTO_REMEDIATE_MAX_SEVERITY", "SEV-2")

# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------
VOICE_ENABLED: bool = _bool("VOICE_ENABLED", False)

# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
SLACK_ENABLED: bool = _bool("SLACK_ENABLED", False)
SLACK_INTERACTIVE: bool = _bool("SLACK_INTERACTIVE", False)
SLACK_CALL_MODE: str = os.getenv("SLACK_CALL_MODE", "off")
SLACK_BOT_TOKEN: str | None = os.getenv("SLACK_BOT_TOKEN") or None
SLACK_SIGNING_SECRET: str | None = os.getenv("SLACK_SIGNING_SECRET") or None

# ---------------------------------------------------------------------------
# Public URL (for Datadog / Lyzr / Slack callbacks)
# ---------------------------------------------------------------------------
PUBLIC_BACKEND_URL: str | None = os.getenv("PUBLIC_BACKEND_URL") or None
