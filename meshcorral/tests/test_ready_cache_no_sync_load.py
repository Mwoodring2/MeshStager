"""READY cache and sync-load guards (Prime Performance Pass v0.4)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.thumbnail_controller import ThumbnailViewController
from meshcorral.ui.thumbnail_ready_cache import (
    ThumbnailReadyCache,
    validate_bridge_thumbnail_ready,
    validate_raster_source_ready,
)


def _rec(path: str) -> FileRecord:
    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=p.suffix or ".stl",
        parent_folder="f",
        size_bytes=1,
        modified_time=0.0,
    )


class TestThumbnailReadyCache(unittest.TestCase):
    def test_mark_ready_requires_file_on_disk(self) -> None:
        cache = ThumbnailReadyCache()
        with tempfile.TemporaryDirectory() as tmp:
            thumb = Path(tmp) / "thumbnail.png"
            thumb.write_bytes(b"x")
            src = Path(tmp) / "mesh.stl"
            self.assertTrue(cache.mark_ready(src, thumb))
            self.assertTrue(cache.is_ready(src))
            self.assertEqual(cache.get_thumbnail_path(src), str(thumb))

    def test_is_ready_no_disk_stat(self) -> None:
        cache = ThumbnailReadyCache()
        with tempfile.TemporaryDirectory() as tmp:
            thumb = Path(tmp) / "thumbnail.png"
            thumb.write_bytes(b"x")
            src = Path(tmp) / "mesh.stl"
            cache.mark_ready(src, thumb)
        with mock.patch.object(Path, "is_file", side_effect=AssertionError("no disk on is_ready")):
            self.assertTrue(cache.is_ready(src))

    def test_mark_ready_raster_no_bridge_png(self) -> None:
        cache = ThumbnailReadyCache()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "shot.png"
            src.write_bytes(b"x")
            self.assertTrue(cache.mark_ready_raster(src))
            self.assertTrue(validate_raster_source_ready(src))

    def test_validate_bridge_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            thumb = Path(tmp) / "t.png"
            thumb.write_bytes(b"1")
            self.assertTrue(
                validate_bridge_thumbnail_ready(
                    status=BridgeJobStatus.COMPLETE.value,
                    thumbnail_path=str(thumb),
                )
            )
            self.assertFalse(
                validate_bridge_thumbnail_ready(
                    status=BridgeJobStatus.FAILED.value,
                    thumbnail_path=str(thumb),
                )
            )


class TestSyncLoadGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_guard_blocks_qimage_in_paint(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        with mock.patch("meshcorral.ui.thumbnail_controller._in_paint_context", return_value=True):
            with mock.patch("meshcorral.ui.thumbnail_controller.QImage") as qimg:
                out = ctrl._guard_sync_image_load("C:/fake.png")
        self.assertIsNone(out)
        qimg.assert_not_called()

    def test_mark_from_job_result_populates_ready(self) -> None:
        ctrl = ThumbnailViewController()
        with tempfile.TemporaryDirectory() as tmp:
            thumb = Path(tmp) / "thumbnail.png"
            thumb.write_bytes(b"x")
            src = Path(tmp) / "mesh.stl"
            result = BridgeJobResult(
                job_id="j1",
                status=BridgeJobStatus.COMPLETE,
                source_file=str(src),
                thumbnail_path=str(thumb),
                output_dir=str(tmp),
                log_path=None,
                error_message=None,
                metadata_json_path=None,
                job_type="generate_thumbnail",
            )
            ctrl.on_job_result(result, refresh_ui=False)
            self.assertTrue(ctrl.ready_cache().is_ready(src))


if __name__ == "__main__":
    unittest.main()
