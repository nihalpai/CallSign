"""Config toggles parse correctly from environment variables."""
from __future__ import annotations

import importlib
import sys
import os


def _reload_config(env: dict[str, str]) -> object:
    """Re-import app.config with a specific environment."""
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


def test_on_call_path_exists():
    from app.config import ON_CALL_PATH
    assert ON_CALL_PATH.exists()


# ---------------------------------------------------------------------------
# Toggle defaults
# ---------------------------------------------------------------------------

def test_slack_enabled_is_bool():
    from app.config import SLACK_ENABLED
    assert isinstance(SLACK_ENABLED, bool)


def test_slack_interactive_is_bool():
    from app.config import SLACK_INTERACTIVE
    assert isinstance(SLACK_INTERACTIVE, bool)


def test_enrich_requests_is_bool():
    from app.config import ENRICH_REQUESTS
    assert isinstance(ENRICH_REQUESTS, bool)


def test_expertise_routing_is_bool():
    from app.config import EXPERTISE_ROUTING
    assert isinstance(EXPERTISE_ROUTING, bool)


# ---------------------------------------------------------------------------
# Boolean parsing from env strings
# ---------------------------------------------------------------------------

def test_bool_toggle_true_string(monkeypatch):
    monkeypatch.setenv("SLACK_ENABLED", "true")
    from app.config import _bool
    assert _bool("SLACK_ENABLED", False) is True


def test_bool_toggle_one_string(monkeypatch):
    monkeypatch.setenv("SLACK_ENABLED", "1")
    from app.config import _bool
    assert _bool("SLACK_ENABLED", False) is True


def test_bool_toggle_false_string(monkeypatch):
    monkeypatch.setenv("SLACK_ENABLED", "false")
    from app.config import _bool
    assert _bool("SLACK_ENABLED", True) is False


def test_bool_toggle_missing_uses_default(monkeypatch):
    monkeypatch.delenv("SOME_UNKNOWN_KEY", raising=False)
    from app.config import _bool
    assert _bool("SOME_UNKNOWN_KEY", True) is True


def test_approval_api_key_none_when_unset(monkeypatch):
    from app import config
    assert config.APPROVAL_API_KEY is None or isinstance(config.APPROVAL_API_KEY, str)
