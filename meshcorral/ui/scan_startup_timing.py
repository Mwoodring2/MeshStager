"""Timing helpers for folder-scan startup (UI-thread audit)."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

LOG_PREFIX = "SCAN_STARTUP_TIMING"


class ScanStartupTimer:
    """
    Log elapsed milliseconds between scan-startup milestones.

    Uses :data:`LOG_PREFIX` so logs are easy to filter during RC responsiveness work.
    """

    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self._last = self._t0

    def mark(self, step: str, *, extra: str = "") -> None:
        """Record *step* with delta and total elapsed time in milliseconds."""
        now = time.perf_counter()
        step_ms = (now - self._last) * 1000.0
        total_ms = (now - self._t0) * 1000.0
        self._last = now
        suffix = f" {extra}" if extra else ""
        logger.info(
            "%s %s: step_ms=%.1f total_ms=%.1f%s",
            LOG_PREFIX,
            step,
            step_ms,
            total_ms,
            suffix,
        )
