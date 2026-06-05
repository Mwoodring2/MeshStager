"""Tests for raster thumbnail routing in :class:`~meshcorral.ui.thumbnail_controller.ThumbnailViewController`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.thumbnail_controller import ThumbnailViewController


_ONE_BY_ONE_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01"
    b"\xe2!\xbc3"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestImageThumbnailRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        inst = QApplication.instance()
        cls._app = inst if inst is not None else QApplication([])

    def tearDown(self) -> None:
        ctrl = getattr(self, "_ctrl", None)
        if ctrl is not None:
            ctrl.request_shutdown(timeout_ms=500)
            self._ctrl = None

    def test_paint_decode_path_allows_raster_in_non_prime_paint(self) -> None:
        """Regression: non-prime paint must schedule async decode for raster sources."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.png"
            p.write_bytes(_ONE_BY_ONE_PNG)
            rec = FileRecord(
                path=p,
                name=p.name,
                extension=".png",
                parent_folder=p.parent.name,
                size_bytes=p.stat().st_size,
                modified_time=0.0,
            )
            ctrl = ThumbnailViewController()
            self._ctrl = ctrl
            ctrl.set_prime_perf_mode(False)
            with mock.patch(
                "meshcorral.ui.thumbnail_controller._in_paint_context",
                return_value=True,
            ):
                load_path = ctrl._paint_decode_path(rec)
            self.assertEqual(load_path, str(p))

    def test_decoration_for_image_schedules_load_without_blender_index(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.png"
            p.write_bytes(_ONE_BY_ONE_PNG)
            rec = FileRecord(
                path=p,
                name=p.name,
                extension=".png",
                parent_folder=p.parent.name,
                size_bytes=p.stat().st_size,
                modified_time=0.0,
            )

            ctrl = ThumbnailViewController()
            self._ctrl = ctrl
            # Prevent the threadpool from immediately consuming and clearing inflight.
            ctrl._pool.start = lambda _r: None  # type: ignore[method-assign]

            _ = ctrl.decoration_for(rec)
            key = _norm_path_key(rec.path)
            cache_key = ctrl._pixmap_cache_key(key, ctrl.display_pixel_size())
            self.assertIn(cache_key, ctrl._decoding_keys)

    def test_table_decoration_for_schedules_separate_table_decode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.png"
            p.write_bytes(_ONE_BY_ONE_PNG)
            rec = FileRecord(
                path=p,
                name=p.name,
                extension=".png",
                parent_folder=p.parent.name,
                size_bytes=p.stat().st_size,
                modified_time=0.0,
            )

            ctrl = ThumbnailViewController()
            self._ctrl = ctrl
            ctrl._pool.start = lambda _r: None  # type: ignore[method-assign]

            _ = ctrl.table_decoration_for(rec)
            key = _norm_path_key(rec.path)
            cache_key = ctrl._pixmap_cache_key(key, ctrl.table_thumb_pixel_size())
            self.assertIn(cache_key, ctrl._decoding_keys)

    def test_clear_thumbnail_cache_resets_inflight_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.png"
            p.write_bytes(_ONE_BY_ONE_PNG)
            rec = FileRecord(
                path=p,
                name=p.name,
                extension=".png",
                parent_folder=p.parent.name,
                size_bytes=p.stat().st_size,
                modified_time=0.0,
            )
            ctrl = ThumbnailViewController()
            self._ctrl = ctrl
            ctrl._pool.start = lambda _r: None  # type: ignore[method-assign]
            _ = ctrl.decoration_for(rec)
            self.assertGreaterEqual(ctrl.cache_stats()["pending_loads"], 1)
            ctrl.clear_thumbnail_cache()
            stats = ctrl.cache_stats()
            self.assertEqual(stats["pending_loads"], 0)
            self.assertEqual(stats["cache_items"], 0)
            self.assertEqual(ctrl.decoding_count(), 0)


if __name__ == "__main__":
    unittest.main()

