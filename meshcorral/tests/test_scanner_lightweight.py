"""Tests for Prime v0.7 lightweight scanner — no ``Path.stat()`` on the hot path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from meshcorral.services import scanner as scanner_module
from meshcorral.services.scanner import iter_scan_file_records


class TestLightweightScan(unittest.TestCase):
    """The lightweight scan must not stat files and must emit ``None`` metadata."""

    def _populate(self, root: Path) -> None:
        for name in ("a.obj", "b.stl", "c.fbx"):
            (root / name).write_bytes(b"x")

    def test_lightweight_returns_none_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._populate(root)
            records = list(
                iter_scan_file_records(root, recursive=False, lightweight=True)
            )
        self.assertEqual(len(records), 3)
        for rec in records:
            self.assertIsNone(rec.size_bytes)
            self.assertIsNone(rec.modified_time)
            self.assertFalse(rec.is_metadata_enriched())

    def test_default_still_eager_stats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._populate(root)
            records = list(iter_scan_file_records(root, recursive=False))
        for rec in records:
            self.assertIsNotNone(rec.size_bytes)
            self.assertIsNotNone(rec.modified_time)
            self.assertTrue(rec.is_metadata_enriched())

    def test_lightweight_recursive_returns_none_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sub = root / "sub"
            sub.mkdir()
            (sub / "x.obj").write_bytes(b"x")
            (root / "y.obj").write_bytes(b"y")
            records = list(
                iter_scan_file_records(root, recursive=True, lightweight=True)
            )
        self.assertEqual(len(records), 2)
        for rec in records:
            self.assertIsNone(rec.size_bytes)

    def test_lightweight_does_not_call_path_stat_in_record_builder(self) -> None:
        """``record_for_path`` must not stat when lightweight=True."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._populate(root)
            with mock.patch.object(
                scanner_module, "FileRecord", wraps=scanner_module.FileRecord
            ) as wrapped:
                records = list(
                    iter_scan_file_records(root, recursive=False, lightweight=True)
                )
            self.assertEqual(len(records), 3)
            for call in wrapped.call_args_list:
                kwargs = call.kwargs
                self.assertIsNone(kwargs.get("size_bytes"))
                self.assertIsNone(kwargs.get("modified_time"))


if __name__ == "__main__":
    unittest.main()
