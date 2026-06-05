"""Cooperative cancellation token for background folder scans."""

from __future__ import annotations

import threading


class ScanCancelToken:
    """
    Thread-safe cancel flag shared between the UI thread and a scan worker.

    The worker polls :meth:`is_canceled` at safe checkpoints; the UI calls
    :meth:`request_cancel` without blocking on thread teardown.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def request_cancel(self) -> None:
        """Ask the active scan to stop at the next checkpoint."""
        self._event.set()

    def is_canceled(self) -> bool:
        """True after :meth:`request_cancel` has been called."""
        return self._event.is_set()
