"""
Logging configuration for CallSign.

Call configure_logging() once at startup (done from config.py import).
Use get_logger(__name__) in every module.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "callsign.log"
_FORMAT = "%(asctime)s %(levelname)s %(name)s | %(message)s"
_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    _LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    rotating = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    rotating.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(rotating)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
