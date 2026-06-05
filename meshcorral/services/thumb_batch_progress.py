"""Coarse 1 Hz thumbnail batch progress for Prime Performance Pass UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThumbBatchProgress:
    """Snapshot of an in-flight thumbnail generation batch."""

    active: bool
    completed: int
    total: int

    def label(self) -> str:
        """Status line for the footer or status bar."""
        if not self.active or self.total <= 0:
            return ""
        return f"Generating thumbnails… ({self.completed}/{self.total})"


class ThumbBatchProgressTracker:
    """
    Track completed vs total jobs for a batch without per-job UI updates.

    *total* is set when a batch enqueue finishes; each completion increments
    :attr:`completed` until :meth:`finish` is called.
    """

    def __init__(self) -> None:
        self._active: bool = False
        self._completed: int = 0
        self._total: int = 0

    def start_batch(self, total: int) -> None:
        """Begin tracking a new batch (resets completed count)."""
        self._active = int(total) > 0
        self._total = max(0, int(total))
        self._completed = 0

    def add_to_total(self, count: int) -> None:
        """Extend the expected batch size (e.g. scroll preload adds jobs)."""
        if count <= 0:
            return
        self._total += int(count)
        if self._total > 0:
            self._active = True

    def note_completion(self) -> None:
        """Record one finished bridge job."""
        if not self._active:
            return
        self._completed += 1
        if self._completed >= self._total:
            self.finish()

    def finish(self) -> None:
        """Mark the batch complete (footer may return to idle)."""
        self._active = False

    def snapshot(self) -> ThumbBatchProgress:
        return ThumbBatchProgress(
            active=self._active,
            completed=self._completed,
            total=self._total,
        )

    def active(self) -> bool:
        return self._active
