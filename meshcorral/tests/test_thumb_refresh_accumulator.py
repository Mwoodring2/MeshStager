"""Tests for batched thumbnail UI refresh."""

from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from meshcorral.services.thumb_refresh_accumulator import (
    DEFAULT_INTERVAL_MS,
    ThumbRefreshAccumulator,
)
from meshcorral.services.thumb_batch_progress import ThumbBatchProgressTracker
from meshcorral.ui.thumb_row_emit import row_indices_for_path_keys
from meshcorral.models.file_record import FileRecord


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


class TestThumbRefreshAccumulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_batches_paths(self) -> None:
        acc = ThumbRefreshAccumulator(interval_ms=50)
        batches: list[frozenset[str]] = []

        def _on_flush(keys: frozenset[str]) -> None:
            batches.append(keys)

        acc.flush_requested.connect(_on_flush)
        acc.add_path(Path("C:/a/one.stl"))
        acc.add_path(Path("C:/a/two.stl"))
        self.assertEqual(acc.pending_count(), 2)
        acc.flush_now()
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 2)

    def test_interval_default(self) -> None:
        self.assertEqual(DEFAULT_INTERVAL_MS, 250)


class TestThumbBatchProgress(unittest.TestCase):
    def test_label(self) -> None:
        tracker = ThumbBatchProgressTracker()
        tracker.start_batch(50)
        tracker.note_completion()
        snap = tracker.snapshot()
        self.assertEqual(snap.label(), "Generating thumbnails… (1/50)")


class TestVisibleRowEmit(unittest.TestCase):
    def test_visible_only_rows(self) -> None:
        records = [_rec(f"C:/a/{i}.stl") for i in range(10)]
        keys = frozenset({_norm_path_key(records[5].path), _norm_path_key(records[8].path)})
        rows = row_indices_for_path_keys(records, keys, visible_rows=[5, 6, 7])
        self.assertEqual(rows, [5])


def _norm_path_key(p: Path) -> str:
    from meshcorral.app.bridge.thumb_index import _norm_path_key as norm

    return norm(p)


if __name__ == "__main__":
    unittest.main()
