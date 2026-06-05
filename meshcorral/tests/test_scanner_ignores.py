"""Tests for scan ignore rules (system/metadata junk should not appear in results)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.services.scanner import scan_folder


class TestScannerIgnores(unittest.TestCase):
    def test_recursive_scan_prunes_ignored_dirs_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            # Real asset.
            (root / "good.obj").write_text("o x\n", encoding="utf-8")

            # macOS metadata folder + sidecar.
            ad = root / ".AppleDouble"
            ad.mkdir(parents=True, exist_ok=True)
            (ad / "bad.obj").write_text("metadata\n", encoding="utf-8")

            # dot-underscore sidecar next to a real file.
            (root / "._sidecar.obj").write_text("metadata\n", encoding="utf-8")

            # Windows-ish junk.
            (root / "Thumbs.db").write_text("junk\n", encoding="utf-8")
            (root / "desktop.ini").write_text("junk\n", encoding="utf-8")

            # Ignored folders.
            (root / "$RECYCLE.BIN").mkdir(parents=True, exist_ok=True)
            (root / "$RECYCLE.BIN" / "trash.obj").write_text("o x\n", encoding="utf-8")
            (root / "System Volume Information").mkdir(parents=True, exist_ok=True)
            (root / "System Volume Information" / "sys.obj").write_text("o x\n", encoding="utf-8")

            recs = scan_folder(root, recursive=True, allowed_extensions={".obj"})
            names = {r.path.name for r in recs}

            self.assertIn("good.obj", names)
            self.assertNotIn("bad.obj", names)
            self.assertNotIn("._sidecar.obj", names)
            self.assertNotIn("trash.obj", names)
            self.assertNotIn("sys.obj", names)

    def test_non_recursive_scan_ignores_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "good.obj").write_text("o x\n", encoding="utf-8")
            (root / "._bad.obj").write_text("metadata\n", encoding="utf-8")

            recs = scan_folder(root, recursive=False, allowed_extensions={".obj"})
            names = {r.path.name for r in recs}
            self.assertEqual(names, {"good.obj"})


if __name__ == "__main__":
    unittest.main()

