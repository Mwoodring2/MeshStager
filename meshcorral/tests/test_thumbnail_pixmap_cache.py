"""Tests for :class:`~meshcorral.ui.thumbnail_pixmap_cache.ThumbnailPixmapLRUCache`."""

from __future__ import annotations

import unittest
from unittest import mock

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.ui.thumbnail_pixmap_cache import ThumbnailPixmapLRUCache, pixmap_memory_bytes


class _FakePixmap:
    """Lightweight pixmap stand-in for unit tests (no Qt GUI surface)."""

    def __init__(self, w: int, h: int) -> None:
        self._w = int(w)
        self._h = int(h)

    def isNull(self) -> bool:
        return False

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h

    def devicePixelRatio(self) -> float:
        return 1.0


def _pixmap(w: int, h: int) -> _FakePixmap:
    return _FakePixmap(w, h)


class TestThumbnailPixmapLRUCache(unittest.TestCase):
    def test_lru_evicts_oldest_by_count(self) -> None:
        cache = ThumbnailPixmapLRUCache(max_items=2, max_bytes=1024 * 1024 * 1024)
        cache.put("a", _pixmap(8, 8))
        cache.put("b", _pixmap(8, 8))
        cache.put("c", _pixmap(8, 8))
        self.assertIsNone(cache.get("a"))
        self.assertIsNotNone(cache.get("b"))
        self.assertIsNotNone(cache.get("c"))
        stats = cache.stats()
        self.assertGreaterEqual(stats["evictions"], 1)
        self.assertEqual(stats["cache_items"], 2)

    def test_lru_evicts_by_byte_budget(self) -> None:
        pm = _pixmap(100, 100)
        one = pixmap_memory_bytes(pm)
        cache = ThumbnailPixmapLRUCache(max_items=100, max_bytes=one * 2 + 1)
        cache.put("a", pm)
        cache.put("b", _pixmap(100, 100))
        cache.put("c", _pixmap(100, 100))
        self.assertIsNone(cache.get("a"))
        self.assertGreaterEqual(cache.stats()["evictions"], 1)

    def test_clear_empties_items_and_stats(self) -> None:
        cache = ThumbnailPixmapLRUCache(max_items=8, max_bytes=1024 * 1024)
        cache.put("x", _pixmap(4, 4))
        cache.get("x")
        cache.clear()
        stats = cache.stats()
        self.assertEqual(stats["cache_items"], 0)
        self.assertEqual(stats["cache_bytes"], 0)
        self.assertIsNone(cache.get("x"))

    def test_remove_single_key(self) -> None:
        cache = ThumbnailPixmapLRUCache(max_items=8, max_bytes=1024 * 1024)
        cache.put("k", _pixmap(4, 4))
        cache.remove("k")
        self.assertIsNone(cache.get("k"))

    def test_remove_matching_prefix(self) -> None:
        cache = ThumbnailPixmapLRUCache(max_items=8, max_bytes=1024 * 1024)
        cache.put("src|96", _pixmap(4, 4))
        cache.put("src|48", _pixmap(4, 4))
        cache.put("other|96", _pixmap(4, 4))
        cache.remove_matching_prefix("src")
        self.assertIsNone(cache.get("src|96"))
        self.assertIsNotNone(cache.get("other|96"))


class TestControllerCacheIntegration(unittest.TestCase):
    def test_cache_hit_skips_decode_enqueue(self) -> None:
        from pathlib import Path

        from meshcorral.models.file_record import FileRecord
        from meshcorral.ui.thumbnail_controller import ThumbnailViewController

        ctrl = ThumbnailViewController()
        key = _norm_path_key(Path("C:/a/photo.png"))
        cache_key = ctrl._pixmap_cache_key(key, 96)
        ctrl._pixmap_lru.put(cache_key, _pixmap(32, 32))
        rec = FileRecord(
            path=Path("C:/a/photo.png"),
            name="photo.png",
            extension=".png",
            parent_folder="a",
            size_bytes=1,
            modified_time=0.0,
        )
        ctrl.set_record_visible_fn(lambda _r: True)
        ctrl.ready_cache().mark_ready_raster(rec.path)
        self.assertFalse(ctrl._should_start_decode(rec, px=96))

    def test_duplicate_decode_suppressed(self) -> None:
        from pathlib import Path

        from meshcorral.ui.thumbnail_controller import ThumbnailViewController

        ctrl = ThumbnailViewController()
        key = _norm_path_key(Path("C:/x.png"))
        px = ctrl.display_pixel_size()
        cache_key = ctrl._pixmap_cache_key(key, px)
        ctrl._decoding_keys.add(cache_key)
        started: list[str] = []
        ctrl._pool.start = lambda _r: started.append("run")  # type: ignore[method-assign]
        ctrl._start_gallery_load(key, "C:/x.png")
        self.assertEqual(started, [])


if __name__ == "__main__":
    unittest.main()
