"""Parity between :func:`~meshcorral.services.scanner.scan_folder` and streaming iterator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.services.scanner import (
    iter_scan_file_records,
    scan_folder,
    scan_folder_sort_key,
)


class TestScanStreamingParity(unittest.TestCase):
    """``scan_folder`` output matches materialized iterator + sort."""

    def test_iter_matches_scan_folder_multiset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.obj").write_text("o\n", encoding="utf-8")
            sub = root / "a_sub"
            sub.mkdir()
            (sub / "a.obj").write_text("o\n", encoding="utf-8")
            (root / "skip.txt").write_text("x", encoding="utf-8")

            streamed = list(
                iter_scan_file_records(
                    root, recursive=True, allowed_extensions={".obj"}
                )
            )
            batched = scan_folder(
                root, recursive=True, allowed_extensions={".obj"}
            )
            self.assertEqual(
                sorted({r.path for r in streamed}),
                sorted({r.path for r in batched}),
            )
            self.assertEqual(
                sorted(streamed, key=scan_folder_sort_key),
                batched,
            )

    def test_after_dir_scanned_fires_without_matches_in_dir(self) -> None:
        """Callback runs after each directory, including before any file is matched."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub = root / "sub"
            sub.mkdir()
            (sub / "deep.obj").write_text("o\n", encoding="utf-8")

            seen: list[tuple[int, Path]] = []

            def hook(n: int, p: Path) -> None:
                seen.append((n, p))

            list(
                iter_scan_file_records(
                    root,
                    recursive=True,
                    allowed_extensions={".obj"},
                    after_dir_scanned=hook,
                )
            )
            self.assertTrue(seen)
            self.assertEqual(seen[0][0], 0)


if __name__ == "__main__":
    unittest.main()
