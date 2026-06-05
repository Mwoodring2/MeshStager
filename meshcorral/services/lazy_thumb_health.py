"""Lazy thumbnail health resolution (visible-first, no full scan on index complete)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth


class LazyThumbHealthResolver:
    """
    Defer :class:`ThumbHealth` lookups until rows are visible or explicitly resolved.

    When lazy mode is off, delegates directly to the underlying resolver (index lookup).
    """

    def __init__(self, resolve_fn: Callable[[FileRecord], ThumbHealth]) -> None:
        self._resolve_fn = resolve_fn
        self._cache: dict[str, ThumbHealth] = {}
        self._lazy_enabled: bool = False

    def set_lazy_enabled(self, enabled: bool) -> None:
        """Enable or disable lazy (pending) health for unresolved rows."""
        self._lazy_enabled = bool(enabled)
        if not self._lazy_enabled:
            self.clear()

    def lazy_enabled(self) -> bool:
        return self._lazy_enabled

    def clear(self) -> None:
        """Drop cached health (after scan or index refresh)."""
        self._cache.clear()

    def invalidate_key(self, path_key: str) -> None:
        """Drop one cached entry when a bridge job updates a source file."""
        self._cache.pop(path_key, None)

    def thumb_health(self, record: FileRecord) -> ThumbHealth:
        """
        Return cached health, pending when lazy, or resolve immediately when not lazy.
        """
        if not self._lazy_enabled:
            return self._resolve_fn(record)
        key = _norm_path_key(record.path)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        return ThumbHealth.PENDING

    def resolve(self, record: FileRecord) -> ThumbHealth:
        """Resolve and cache health for *record*."""
        health = self._resolve_fn(record)
        self._cache[_norm_path_key(record.path)] = health
        return health

    def resolve_many(self, records: Iterable[FileRecord]) -> None:
        """Resolve health for each record (idempotent)."""
        for record in records:
            self.resolve(record)

    def resolve_many_changed(self, records: Iterable[FileRecord]) -> list[FileRecord]:
        """
        Resolve health for each record; return only rows whose health value changed.

        Avoids redundant ``dataChanged`` emissions when the viewport pass re-runs
        on an idle timer with no new index information.
        """
        changed: list[FileRecord] = []
        for record in records:
            key = _norm_path_key(record.path)
            prev = self._cache.get(key)
            health = self._resolve_fn(record)
            if prev != health:
                self._cache[key] = health
                changed.append(record)
        return changed

    def resolved_count(self) -> int:
        return len(self._cache)

    def pending_in(self, records: Sequence[FileRecord]) -> list[FileRecord]:
        """Records still pending under lazy mode."""
        if not self._lazy_enabled:
            return []
        out: list[FileRecord] = []
        for record in records:
            key = _norm_path_key(record.path)
            if key not in self._cache:
                out.append(record)
        return out
