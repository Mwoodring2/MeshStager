"""Bounded LRU cache for decoded thumbnail pixmaps (Prime Performance v0.6)."""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any, Final

from PySide6.QtGui import QPixmap

_DEFAULT_MAX_ITEMS: Final[int] = 512
_DEFAULT_MAX_BYTES: Final[int] = 256 * 1024 * 1024
_BYTES_PER_PIXEL: Final[int] = 4


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except ValueError:
        return int(default)
    return value if value > 0 else int(default)


def pixmap_memory_bytes(pixmap: QPixmap) -> int:
    """Estimate resident bytes for *pixmap* (RGBA, device pixel ratio aware)."""
    if pixmap.isNull():
        return 0
    w = max(0, int(pixmap.width()))
    h = max(0, int(pixmap.height()))
    ratio = float(pixmap.devicePixelRatio() or 1.0)
    physical_w = max(1, int(w * ratio))
    physical_h = max(1, int(h * ratio))
    return physical_w * physical_h * _BYTES_PER_PIXEL


def default_max_items() -> int:
    """Max pixmap entries from ``ROUNDUP_THUMB_CACHE_MAX_ITEMS`` (default 512)."""
    return _env_positive_int("ROUNDUP_THUMB_CACHE_MAX_ITEMS", _DEFAULT_MAX_ITEMS)


def default_max_bytes() -> int:
    """Max estimated bytes from ``ROUNDUP_THUMB_CACHE_MAX_MB`` (default 256)."""
    mb = _env_positive_int("ROUNDUP_THUMB_CACHE_MAX_MB", _DEFAULT_MAX_BYTES // (1024 * 1024))
    return int(mb) * 1024 * 1024


class ThumbnailPixmapLRUCache:
    """
    Thread-safe LRU of decoded :class:`QPixmap` thumbnails keyed by caller path key.

    Evicts oldest entries when count or estimated memory exceeds configured limits.
    """

    def __init__(
        self,
        *,
        max_items: int | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self._max_items = max(1, int(max_items if max_items is not None else default_max_items()))
        self._max_bytes = max(1, int(max_bytes if max_bytes is not None else default_max_bytes()))
        self._lock = threading.Lock()
        self._items: OrderedDict[str, QPixmap] = OrderedDict()
        self._bytes: dict[str, int] = {}
        self._total_bytes: int = 0
        self._evictions: int = 0
        self._hits: int = 0
        self._misses: int = 0

    def peek(self, key: str) -> QPixmap | None:
        """Return a cached pixmap without updating LRU order or hit counters."""
        k = str(key).strip()
        if not k:
            return None
        with self._lock:
            pm = self._items.get(k)
            if pm is None or pm.isNull():
                return None
            return pm

    def get(self, key: str) -> QPixmap | None:
        """Return a cached pixmap and mark *key* most-recently used."""
        k = str(key).strip()
        if not k:
            return None
        with self._lock:
            pm = self._items.get(k)
            if pm is None or pm.isNull():
                if pm is not None:
                    self._drop_key(k)
                self._misses += 1
                return None
            self._items.move_to_end(k)
            self._hits += 1
            return pm

    def put(self, key: str, pixmap: QPixmap) -> None:
        """Insert or refresh *pixmap* under *key*, evicting LRU entries as needed."""
        k = str(key).strip()
        if not k or pixmap.isNull():
            return
        size = pixmap_memory_bytes(pixmap)
        with self._lock:
            if k in self._items:
                self._total_bytes -= self._bytes.get(k, 0)
                self._items.pop(k, None)
                self._bytes.pop(k, None)
            self._items[k] = pixmap
            self._bytes[k] = size
            self._total_bytes += size
            self._items.move_to_end(k)
            self._evict_locked()

    def remove(self, key: str) -> None:
        """Remove a single cache entry."""
        k = str(key).strip()
        if not k:
            return
        with self._lock:
            self._drop_key(k)

    def remove_matching_prefix(self, prefix: str) -> None:
        """Remove all keys equal to *prefix* or starting with ``prefix|``."""
        p = str(prefix).strip()
        if not p:
            return
        with self._lock:
            doomed = [
                k
                for k in list(self._items.keys())
                if k == p or k.startswith(f"{p}|")
            ]
            for k in doomed:
                self._drop_key(k)

    def clear(self) -> None:
        """Drop all cached pixmaps."""
        with self._lock:
            self._items.clear()
            self._bytes.clear()
            self._total_bytes = 0

    def stats(self) -> dict[str, Any]:
        """Snapshot counters and footprint for diagnostics."""
        with self._lock:
            items = len(self._items)
            mb = self._total_bytes / (1024.0 * 1024.0)
            return {
                "cache_items": int(items),
                "cache_mb": round(mb, 2),
                "cache_bytes": int(self._total_bytes),
                "cache_hits": int(self._hits),
                "cache_misses": int(self._misses),
                "evictions": int(self._evictions),
                "max_items": int(self._max_items),
                "max_bytes": int(self._max_bytes),
            }

    def _drop_key(self, key: str) -> None:
        if key not in self._items:
            return
        self._items.pop(key, None)
        self._total_bytes -= self._bytes.pop(key, 0)

    def _evict_locked(self) -> None:
        while self._items and (
            len(self._items) > self._max_items or self._total_bytes > self._max_bytes
        ):
            oldest, _ = self._items.popitem(last=False)
            self._total_bytes -= self._bytes.pop(oldest, 0)
            self._evictions += 1
