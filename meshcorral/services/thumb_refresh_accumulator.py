"""Batched thumbnail row refresh (debounced) to avoid per-job Qt repaints."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from meshcorral.app.bridge.thumb_index import _norm_path_key

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MS: int = 250


class ThumbRefreshAccumulator(QObject):
    """
    Coalesce many completed thumbnail paths into one UI refresh per interval.

    Call :meth:`add_path` or :meth:`add_path_key` when a bridge job finishes; a single
    :meth:`flush_requested` emission fires after :data:`DEFAULT_INTERVAL_MS` of quiet time.
    """

    flush_requested = Signal(object)  # frozenset[str] normalized path keys

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> None:
        super().__init__(parent)
        self._interval_ms = max(1, int(interval_ms))
        self._pending: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._flush)

    def add_path(self, path: Path) -> None:
        """Queue a filesystem path for the next batched refresh."""
        self.add_path_key(_norm_path_key(path))

    def add_path_key(self, path_key: str) -> None:
        """Queue a normalized path key for the next batched refresh."""
        key = str(path_key).strip()
        if not key:
            return
        self._pending.add(key)
        if not self._timer.isActive():
            self._timer.start(self._interval_ms)

    def pending_count(self) -> int:
        """Number of path keys waiting for the next flush."""
        return len(self._pending)

    def flush_now(self) -> None:
        """Flush immediately (tests and shutdown)."""
        self._timer.stop()
        self._flush()

    def cancel_pending(self) -> None:
        """Stop the debounce timer and drop queued keys without emitting."""
        self._timer.stop()
        self._pending.clear()

    def _flush(self) -> None:
        if not self._pending:
            return
        batch = frozenset(self._pending)
        self._pending.clear()
        logger.debug("ThumbRefreshAccumulator flush: %s path(s)", len(batch))
        self.flush_requested.emit(batch)
