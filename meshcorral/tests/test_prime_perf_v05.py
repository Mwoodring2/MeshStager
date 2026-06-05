"""Prime Performance Pass v0.5 — unified READY thumbnail state."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.app.bridge.visible_thumb_queue import (
    is_raster_thumbnail_extension,
    select_raster_decode_candidates,
)
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.thumbnail_controller import ThumbnailViewController
from meshcorral.ui.thumbnail_ready_cache import ThumbnailReadyCache, validate_raster_source_ready

_ONE_BY_ONE_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01"
    b"\xe2!\xbc3"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _png_rec(tmp: Path, name: str = "a.png") -> FileRecord:
    p = tmp / name
    p.write_bytes(_ONE_BY_ONE_PNG)
    return FileRecord(
        path=p,
        name=p.name,
        extension=".png",
        parent_folder=tmp.name,
        size_bytes=p.stat().st_size,
        modified_time=0.0,
    )


class TestRasterReadyCache(unittest.TestCase):
    def test_mark_ready_raster_self_thumb(self) -> None:
        cache = ThumbnailReadyCache()
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "photo.jpg"
            src.write_bytes(b"jpeg-bytes")
            self.assertTrue(cache.mark_ready_raster(src))
            self.assertTrue(cache.is_ready(src))
            self.assertEqual(cache.get_thumbnail_path(src), str(src))

    def test_validate_raster_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.webp"
            p.write_bytes(b"1")
            self.assertTrue(validate_raster_source_ready(p))
            self.assertFalse(validate_raster_source_ready(Path(td) / "missing.webp"))


class TestRasterVisibleQueue(unittest.TestCase):
    def test_select_raster_candidates_skips_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            r1 = _png_rec(tmp, "1.png")
            r2 = _png_rec(tmp, "2.png")
            cache = ThumbnailReadyCache()
            cache.mark_ready_raster(r1.path)
            picked = select_raster_decode_candidates(
                [r1, r2],
                is_ready=lambda r: cache.is_ready(r.path),
                cap=10,
                unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
            )
            self.assertEqual(len(picked), 1)
            self.assertEqual(picked[0].name, "2.png")

    def test_is_raster_extension(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = _png_rec(Path(td))
            self.assertTrue(is_raster_thumbnail_extension(rec))


class TestPrimeImageDecode(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_should_start_decode_when_ready_and_visible(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = _png_rec(Path(td))
            ctrl = ThumbnailViewController()
            ctrl.set_prime_perf_mode(True)
            ctrl.ready_cache().mark_ready_raster(rec.path)
            ctrl.set_record_visible_fn(lambda _r: True)
            self.assertTrue(ctrl._should_start_decode(rec, px=ctrl.display_pixel_size()))

    def test_should_not_decode_when_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = _png_rec(Path(td))
            ctrl = ThumbnailViewController()
            ctrl.set_prime_perf_mode(True)
            ctrl.set_record_visible_fn(lambda _r: True)
            self.assertFalse(ctrl._should_start_decode(rec, px=ctrl.display_pixel_size()))
            self.assertEqual(ctrl.visual_state(rec), ThumbVisualState.PLACEHOLDER)

    def test_async_raster_primer_marks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = _png_rec(Path(td))
            ctrl = ThumbnailViewController()
            ctrl._primer_pool.start = lambda runnable: runnable.run()  # type: ignore[method-assign]
            ctrl.prime_raster_ready_async([rec])
            loop = QCoreApplication.instance()
            if loop is not None:
                loop.processEvents()
            self.assertTrue(ctrl.ready_cache().is_ready(rec.path))
            ctrl.request_shutdown(timeout_ms=500)

    def test_paint_decode_path_uses_ready_cache_in_prime(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = _png_rec(Path(td))
            ctrl = ThumbnailViewController()
            ctrl.set_prime_perf_mode(True)
            ctrl.ready_cache().mark_ready_raster(rec.path)
            with mock.patch("meshcorral.ui.thumbnail_controller._in_paint_context", return_value=True):
                path = ctrl._paint_decode_path(rec)
            self.assertEqual(path, str(rec.path))

    def test_decoding_count_tracks_inflight(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rec = _png_rec(Path(td))
            ctrl = ThumbnailViewController()
            key = _norm_path_key(rec.path)
            cache_key = ctrl._pixmap_cache_key(key, 96)
            self.assertEqual(ctrl.decoding_count(), 0)
            ctrl._decoding_keys.add(cache_key)
            self.assertEqual(ctrl.decoding_count(), 1)
            ctrl._decoding_keys.discard(cache_key)
            self.assertEqual(ctrl.decoding_count(), 0)


if __name__ == "__main__":
    unittest.main()
