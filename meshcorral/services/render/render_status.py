"""UI-facing render pipeline status (background workers)."""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

_notifier: "RenderStatusNotifier | None" = None


class RenderStatusNotifier(QObject):
    """Broadcasts short status strings to the main window footer."""

    status_changed = Signal(str)

    def notify(self, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return
        self.status_changed.emit(text)


def get_render_status_notifier() -> RenderStatusNotifier:
    """Return the process-wide notifier (creates on first use)."""
    global _notifier
    if _notifier is None:
        _notifier = RenderStatusNotifier()
    return _notifier


def render_status_callback() -> Callable[[str], None]:
    """Callback suitable for :class:`RenderTimingProfiler`."""

    def _emit(message: str) -> None:
        get_render_status_notifier().notify(message)

    return _emit
