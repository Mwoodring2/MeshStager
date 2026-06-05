"""Tests for :func:`meshcorral.services.scanner.scan_folder` extension filtering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.app.config import SUPPORTED_3D_EXTENSIONS, SUPPORTED_IMAGE_EXTENSIONS
from meshcorral.services.scanner import scan_folder


class TestScannerAllowedExtensions(unittest.TestCase):
    """``allowed_extensions`` limits which files are collected."""

    def test_respects_subset_for_3d(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.stl").write_bytes(b"")
            (root / "notes.txt").write_text("x", encoding="utf-8")
            (root / "b.png").write_bytes(b"")
            recs = scan_folder(
                root, recursive=False, allowed_extensions=SUPPORTED_3D_EXTENSIONS
            )
            names = {r.name for r in recs}
            self.assertEqual(names, {"a.stl"})

    def test_image_mode_ignores_stl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.stl").write_bytes(b"")
            (root / "b.png").write_bytes(b"")
            recs = scan_folder(
                root, recursive=False, allowed_extensions=SUPPORTED_IMAGE_EXTENSIONS
            )
            names = {r.name for r in recs}
            self.assertEqual(names, {"b.png"})
