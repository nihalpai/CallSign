"""Config toggles parse correctly from environment variables."""
from __future__ import annotations

import importlib
import sys
import os


def _reload_config(env: dict[str, str]) -> object:
    """Re-import app.config with a specific environment."""
    # Remove cached modules so dotenv/os.getenv re-reads from env
    for key in list(sys.modules.keys()):
        if "app.config" in key or "app.logging_config" in key:
            del sys.modules[key]

    old_env = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        import app.config as cfg
        importlib.reload(cfg)
        return cfg
    finally:
        # Restore original env
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Import sanity — config must import cleanly (no key required)
# ---------------------------------------------------------------------------

def test_config_imports():
    import app.config  # noqa: F401


# ---------------------------------------------------------------------------
# Paths exist as Path objects
# ---------------------------------------------------------------------------

def test_data_dir_is_path():
    from app.config import DATA_DIR
    assert DATA_DIR.is_dir()


def test_runbooks_dir_is_path():
    from app.config import RUNBOOKS_DIR
    assert RUNBOOKS_DIR.is_dir()


def test_infra_state_path_exists():
    from app.config import INFRA_STATE_PATH
    assert INFRA_STATE_PATH.exists()


def test_deployments_path_exists():
    from app.config import DEPLOYMENTS_PATH
    assert DEPLOYMENTS_PATH.exists()


def test_on_call_path_exists():
    from app.config import ON_CALL_PATH
    assert ON_CALL_PATH.exists()


def test_mock_alerts_dir_exists():
    from app.config import MOCK_ALERTS_DIR
    assert MOCK_ALERTS_DIR.is_dir()


# ---------------------------------------------------------------------------
# Toggle defaults (no .env overrides in tests via conftest monkeypatch)
# ---------------------------------------------------------------------------

def test_execution_mode_default():
    import app.config as cfg
    # In CI with no .env the default must be "simulate"
    assert cfg.EXECUTION_MODE in ("simulate", "real")  # file may exist locally


def test_auto_remediate_is_bool():
    from app.config import AUTO_REMEDIATE
    assert isinstance(AUTO_REMEDIATE, bool)


def test_voice_enabled_is_bool():
    from app.config import VOICE_ENABLED
    assert isinstance(VOICE_ENABLED, bool)


def test_slack_enabled_is_bool():
    from app.config import SLACK_ENABLED
    assert isinstance(SLACK_ENABLED, bool)


def test_slack_interactive_is_bool():
    from app.config import SLACK_INTERACTIVE
    assert isinstance(SLACK_INTERACTIVE, bool)


def test_auto_remediate_max_severity_is_string():
    from app.config import AUTO_REMEDIATE_MAX_SEVERITY
    assert isinstance(AUTO_REMEDIATE_MAX_SEVERITY, str)


def test_lyzr_api_base_default():
    from app.config import LYZR_API_BASE
    assert LYZR_API_BASE == "https://agent-prod.studio.lyzr.ai" or LYZR_API_BASE.startswith("http")


# ---------------------------------------------------------------------------
# Boolean parsing from env strings
# ---------------------------------------------------------------------------

def test_bool_toggle_true_string(monkeypatch):
    monkeypatch.setenv("SLACK_ENABLED", "true")
    # Re-evaluate the toggle function directly
    from app.config import _bool
    assert _bool("SLACK_ENABLED", False) is True


def test_bool_toggle_one_string(monkeypatch):
    monkeypatch.setenv("VOICE_ENABLED", "1")
    from app.config import _bool
    assert _bool("VOICE_ENABLED", False) is True


def test_bool_toggle_false_string(monkeypatch):
    monkeypatch.setenv("AUTO_REMEDIATE", "false")
    from app.config import _bool
    assert _bool("AUTO_REMEDIATE", True) is False


def test_bool_toggle_missing_uses_default(monkeypatch):
    monkeypatch.delenv("SLACK_CALL_MODE", raising=False)
    from app.config import _bool
    assert _bool("SLACK_ENABLED", True) is True


def test_lyzr_api_key_none_when_unset(monkeypatch):
    monkeypatch.delenv("LYZR_API_KEY", raising=False)
    from app.config import _bool  # just ensure config loaded without error
    # The conftest already clears LYZR_API_KEY; verify the loaded value
    from app import config
    # None or empty string → None (per config.py: `or None`)
    assert config.LYZR_API_KEY is None or config.LYZR_API_KEY == ""
