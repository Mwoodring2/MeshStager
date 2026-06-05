"""Tests for :meth:`FileTableModel.apply_metadata_batch` and the gallery counterpart."""

from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.file_table_model import FileTableModel


class _RoleCounter:
    """Tracks dataChanged signals for assertion."""

    def __init__(self) -> None:
        self.events: list[tuple[int, int, list[int]]] = []

    def __call__(self, top_left, bottom_right, roles) -> None:  # type: ignore[no-untyped-def]
        self.events.append(
            (
                int(top_left.row()),
                int(bottom_right.row()),
                [int(r) for r in roles],
            )
        )


def _rec(path: str) -> FileRecord:
    p = Path(path)
    return FileRecord(path=p, name=p.name, extension=p.suffix, parent_folder=p.parent.name)


class TestApplyMetadataBatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_emits_metadata_columns_only(self) -> None:
        model = FileTableModel()
        records = [_rec(f"C:/a/f{i}.png") for i in range(3)]
        model.set_records(records)
        spy = _RoleCounter()
        model.dataChanged.connect(spy)
        keys = {_norm_path_key(r.path): (1024, 1.0) for r in records}

        touched = model.apply_metadata_batch(keys)

        self.assertEqual(touched, 3)
        self.assertEqual(len(spy.events), 3)
        # Each event must include DisplayRole + UserRole only.
        for _row_lo, _row_hi, roles in spy.events:
            self.assertIn(int(Qt.DisplayRole), roles)
            self.assertIn(int(Qt.UserRole), roles)
        # The model records now carry the new metadata.
        for row in range(3):
            rec = model.record_at(row)
            self.assertIsNotNone(rec)
            self.assertEqual(rec.size_bytes, 1024)
            self.assertEqual(rec.modified_time, 1.0)

    def test_skips_rows_with_unchanged_metadata(self) -> None:
        model = FileTableModel()
        rec = _rec("C:/a/f.png").with_metadata(size_bytes=42, modified_time=2.0)
        model.set_records([rec])
        spy = _RoleCounter()
        model.dataChanged.connect(spy)

        touched = model.apply_metadata_batch({_norm_path_key(rec.path): (42, 2.0)})

        self.assertEqual(touched, 0)
        self.assertEqual(spy.events, [])

    def test_ignores_unknown_keys(self) -> None:
        model = FileTableModel()
        model.set_records([_rec("C:/a/f.png")])
        spy = _RoleCounter()
        model.dataChanged.connect(spy)

        touched = model.apply_metadata_batch({"C:/missing.png": (1, 1.0)})

        self.assertEqual(touched, 0)
        self.assertEqual(spy.events, [])


if __name__ == "__main__":
    unittest.main()
