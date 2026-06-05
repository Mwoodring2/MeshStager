"""Tests for :mod:`meshcorral.app.bridge.auto_thumb_scan`."""

from __future__ import annotations

import unittest
from pathlib import Path

from meshcorral.app.bridge.auto_thumb_scan import (
    filter_auto_thumbnail_records,
    is_auto_thumbnail_extension,
    take_with_cap,
)
from meshcorral.models.file_record import FileRecord
from meshcorral.services.settings_service import SettingsService


def _rec(path: str, ext: str) -> FileRecord:
    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=ext,
        parent_folder="f",
        size_bytes=1,
        modified_time=0.0,
    )


class TestAutoThumbScan(unittest.TestCase):
    def test_is_auto_thumbnail_extension(self) -> None:
        self.assertTrue(
            is_auto_thumbnail_extension(
                _rec("C:/a/mesh.STL", ".stl"),
            )
        )
        self.assertTrue(is_auto_thumbnail_extension(_rec("C:/a/m.obj", ".obj")))
        self.assertTrue(is_auto_thumbnail_extension(_rec("C:/a/m.fbx", ".fbx")))
        self.assertFalse(
            is_auto_thumbnail_extension(
                _rec("O:/assets/.AppleDouble/MyMesh.obj", ".obj"),
            )
        )
        self.assertFalse(
            is_auto_thumbnail_extension(
                _rec("O:/assets/._MyMesh.obj", ".obj"),
            )
        )

    def test_filter(self) -> None:
        a = _rec("C:/a/x.stl", ".stl")
        b = _rec("C:/a/y.ply", ".ply")
        c = _rec("C:/a/z.obj", ".obj")
        d = _rec("C:/a/w.fbx", ".fbx")
        self.assertEqual(filter_auto_thumbnail_records([a, b, c, d]), [a, b, c, d])

    def test_take_with_cap(self) -> None:
        recs = [_rec(f"C:/a/{i}.stl", ".stl") for i in range(5)]
        self.assertEqual(len(take_with_cap(recs, 25)), 5)
        self.assertEqual(len(take_with_cap(recs, 2)), 2)
        self.assertEqual(len(take_with_cap(recs, SettingsService.CAP_AUTO_THUMB_UNLIMITED)), 5)


if __name__ == "__main__":
    unittest.main()
