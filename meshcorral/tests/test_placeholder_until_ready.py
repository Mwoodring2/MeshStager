"""Placeholder icons until READY (no async decode)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication

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


class TestPlaceholderUntilReady(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_not_ready_uses_placeholder_no_pool_start(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        ctrl.set_record_visible_fn(lambda _r: True)
        record = _rec("C:/mesh.stl")
        with mock.patch.object(ctrl, "_start_gallery_load") as start:
            icon = ctrl.decoration_for(record)
        start.assert_not_called()
        self.assertFalse(icon.isNull())
        self.assertGreaterEqual(ctrl.paint_diagnostics().placeholder_paints, 1)

    def test_ready_visible_starts_decode(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        ctrl.set_record_visible_fn(lambda _r: True)
        with tempfile.TemporaryDirectory() as tmp:
            thumb = Path(tmp) / "thumbnail.png"
            thumb.write_bytes(b"x")
            src = Path(tmp) / "mesh.stl"
            ctrl.ready_cache().mark_ready(src, thumb)
            record = _rec(str(src))
            with mock.patch.object(ctrl, "_start_decode") as start:
                ctrl.decoration_for(record)
            start.assert_called_once()
            self.assertGreaterEqual(ctrl.paint_diagnostics().deferred_decode_requests, 1)


if __name__ == "__main__":
    unittest.main()
