"""Logging setup for Roundup.

v1 uses a console logger and a simple per-user log file (Windows-first).
"""

from __future__ import annotations

import logging
from pathlib import Path

from meshcorral.app.config import LOG_DIR


def configure_logging(level: int = logging.INFO) -> None:
    """Configure application-wide logging."""
    root = logging.getLogger()
    if root.handlers:
        # Avoid double configuration in interactive/dev environments.
        root.setLevel(level)
        return

    log_dir = LOG_DIR
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # If we cannot create the directory, we still run with console logging.
        log_dir = Path(".")

    file_handler = logging.FileHandler(log_dir / "roundup.log", encoding="utf-8")
    stream_handler = logging.StreamHandler()

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[file_handler, stream_handler],
    )

