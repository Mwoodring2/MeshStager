"""Scaled gallery pixmaps keyed by path fingerprint and display pixel size."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Final

from PySide6.QtGui import QPixmap

from meshcorral.ui.gallery_perf_constants import gallery_max_visible_build

_DEFAULT_MAX_ITEMS: Final[int] = 512


def gallery_scaled_pixmap_key(
    norm_path_key: str,
    px: int,
    *,
    size_bytes: int | None,
    modified_time: float | None,
) -> str:
    """
    Cache key: normalized path, gallery decode size, and file metadata fingerprint.

    Uses record metadata (size/mtime) so cache invalidates when background stat patches land.
    """
    path = str(norm_path_key).strip()
    sb = int(size_bytes) if size_bytes is not None else 0
    mt = float(modified_time) if modified_time is not None else 0.0
    return f"{path}|{int(px)}|{sb}|{mt:.6f}"


class GalleryScaledPixmapCache:
    """
    Thread-safe LRU of display-ready :class:`QPixmap` instances for gallery paint.

    Separate from decode LRU: avoids repeated ``QIcon.pixmap`` scaling on every paint/scroll.
    """

    def __init__(self, *, max_items: int | None = None) -> None:
        cap = int(max_items if max_items is not None else gallery_max_visible_build() * 4)
        self._max_items = max(_DEFAULT_MAX_ITEMS, min(cap, 8192))
        self._lock = threading.Lock()
        self._items: OrderedDict[str, QPixmap] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> QPixmap | None:
        """Return a cached pixmap and mark *key* most-recently used."""
        k = str(key).strip()
        if not k:
            return None
        with self._lock:
            pm = self._items.get(k)
            if pm is None or pm.isNull():
                if pm is not None:
                    self._items.pop(k, None)
                self._misses += 1
                return None
            self._items.move_to_end(k)
            self._hits += 1
            return pm

    def peek(self, key: str) -> QPixmap | None:
        """Return cached pixmap without updating LRU order."""
        k = str(key).strip()
        if not k:
            return None
        with self._lock:
            pm = self._items.get(k)
            if pm is None or pm.isNull():
                return None
            return pm

    def put(self, key: str, pixmap: QPixmap) -> None:
        """Insert or refresh *pixmap* under *key*."""
        k = str(key).strip()
        if not k or pixmap.isNull():
            return
        with self._lock:
            if k in self._items:
                self._items.pop(k, None)
            self._items[k] = pixmap
            self._items.move_to_end(k)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)

    def remove_matching_path_prefix(self, norm_path_key: str) -> None:
        """Drop entries for one normalized source path (any size/fingerprint)."""
        prefix = f"{str(norm_path_key).strip()}|"
        if not prefix.strip("|"):
            return
        with self._lock:
            doomed = [k for k in self._items if k.startswith(prefix)]
            for k in doomed:
                self._items.pop(k, None)

    def clear(self) -> None:
        """Drop all cached scaled pixmaps."""
        with self._lock:
            self._items.clear()

    def stats(self) -> dict[str, int]:
        """Hit/miss counters for diagnostics and tests."""
        with self._lock:
            return {
                "hits": int(self._hits),
                "misses": int(self._misses),
                "items": len(self._items),
            }
