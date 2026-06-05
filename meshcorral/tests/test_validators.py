"""Tests for validation helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from meshcorral.utils.validators import require_destination_baseline, require_existing_directory


class TestDestinationBaseline(unittest.TestCase):
    """``require_destination_baseline`` for move/copy destinations."""

    def test_existing_directory_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            d = Path(tmp) / "d"
            d.mkdir()
            require_destination_baseline(d, "Dest")

    def test_missing_directory_with_valid_parent_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            d = Path(tmp) / "newdir"
            require_destination_baseline(d, "Dest")

    def test_missing_parent_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            d = Path(tmp) / "missing" / "nested" / "dest"
            with self.assertRaises(ValueError):
                require_destination_baseline(d, "Dest")

    def test_file_path_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "x.txt"
            f.write_text("a")
            with self.assertRaises(ValueError):
                require_destination_baseline(f, "Dest")


class TestRequireExistingDirectory(unittest.TestCase):
    """Scan source still requires a real directory."""

    def test_scan_folder_must_exist(self) -> None:
        with TemporaryDirectory() as tmp:
            d = Path(tmp) / "real"
            d.mkdir()
            require_existing_directory(d, "Scan folder")
