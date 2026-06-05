"""Prime-mode paint path must not touch disk or sync image APIs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

from meshcorral.models.file_record import FileRecord
from meshcorral.ui.thumbnail_controller import ThumbnailViewController


def _rec(path: str) -> FileRecord:
    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=".stl",
        parent_folder="f",
        size_bytes=1,
        modified_time=0.0,
    )


class TestPrimeModePaintNeverHitsDisk(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_decoration_paint_no_is_file(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        record = _rec("C:/not/ready/mesh.stl")
        with mock.patch.object(Path, "is_file", side_effect=AssertionError("paint hit disk")):
            with mock.patch.object(ThumbnailViewController, "_start_gallery_load"):
                ctrl.decoration_for(record)

    def test_decoration_paint_no_qimage(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        record = _rec("C:/mesh.stl")
        with mock.patch.object(QImage, "__init__", side_effect=AssertionError("sync QImage")):
            with mock.patch.object(ctrl, "_start_gallery_load"):
                ctrl.decoration_for(record)

    def test_ready_paint_no_index_disk_stat(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        ctrl.set_record_visible_fn(lambda _r: True)
        with tempfile.TemporaryDirectory() as tmp:
            thumb = Path(tmp) / "thumbnail.png"
            thumb.write_bytes(b"x")
            src = Path(tmp) / "mesh.stl"
            ctrl.ready_cache().mark_ready(src, thumb)
            record = _rec(str(src))
            with mock.patch.object(
                ctrl._index,
                "thumbnail_path_for",
                side_effect=AssertionError("paint used index disk path"),
            ):
                with mock.patch.object(ctrl, "_start_gallery_load"):
                    ctrl.decoration_for(record)


if __name__ == "__main__":
    unittest.main()
