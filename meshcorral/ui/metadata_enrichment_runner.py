"""Qt worker that runs :mod:`~meshcorral.services.metadata_enrichment` off the UI thread."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from meshcorral.services.metadata_enrichment import (
    DEFAULT_BATCH_PAUSE_S,
    DEFAULT_BATCH_SIZE,
    MetadataUpdate,
    iter_metadata_batches,
)

logger = logging.getLogger(__name__)


class MetadataEnrichmentRunner(QObject):
    """
    Worker-side pump for deferred ``stat()`` metadata.

    Owned by a :class:`~PySide6.QtCore.QThread`; the main window builds the
    ``(path_key, Path)`` list from the lightweight scan and triggers
    :meth:`execute_enrichment`. Updates are emitted in chunks via
    :pyattr:`batch_ready`.
    """

    batch_ready: Signal = Signal(object)
    """Emitted with ``list[MetadataUpdate]`` per resolved chunk."""

    enrichment_finished: Signal = Signal(int)
    """Emitted with total updated count when the pump terminates."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cancelled: bool = False

    @Slot()
    def cancel(self) -> None:
        """Request a graceful cooperative stop (next batch boundary)."""
        self._cancelled = True

    def reset(self) -> None:
        """Re-arm the runner for a new pass after a previous cancel."""
        self._cancelled = False

    @Slot(object, int, float)
    def execute_enrichment(
        self,
        entries: object,
        batch_size: int,
        batch_pause_s: float,
    ) -> None:
        """Stat *entries* (``Sequence[(path_key, Path)]``) and emit batches.

        Every signal emit is wrapped in ``try / except RuntimeError`` because a
        teardown race (main thread nulling references, ``deleteLater`` queued
        from a stale ``thr.finished`` connection, etc.) can destroy our C++
        side mid-pump. Raising out of a worker slot crashes the process with
        a Windows stack-buffer-overrun (``0xC0000409``); swallowing the emit
        keeps shutdown deterministic.
        """
        if not isinstance(entries, Sequence):
            self._safe_emit_finished(0)
            return
        pairs = list(entries)
        if not pairs:
            self._safe_emit_finished(0)
            return
        total = 0
        try:
            for batch in iter_metadata_batches(
                pairs,
                batch_size=max(1, int(batch_size or DEFAULT_BATCH_SIZE)),
                batch_pause_s=float(batch_pause_s or DEFAULT_BATCH_PAUSE_S),
                is_cancelled=lambda: self._cancelled,
            ):
                if self._cancelled:
                    break
                total += len(batch)
                if not self._safe_emit_batch(list(batch)):
                    return
        except RuntimeError:
            logger.debug("enrichment iteration raised after C++ deletion")
            return
        self._safe_emit_finished(total)
        logger.debug("metadata runner emitted %s updates", total)

    def _safe_emit_batch(self, batch: list[MetadataUpdate]) -> bool:
        try:
            self.batch_ready.emit(batch)
            return True
        except RuntimeError:
            logger.debug("batch_ready emit aborted: signal source deleted")
            return False

    def _safe_emit_finished(self, total: int) -> None:
        try:
            self.enrichment_finished.emit(total)
        except RuntimeError:
            logger.debug("enrichment_finished emit aborted: signal source deleted")


__all__ = ["MetadataEnrichmentRunner", "MetadataUpdate"]
