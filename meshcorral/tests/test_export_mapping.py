from __future__ import annotations

import unittest
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.ui.file_columns import export_headers, export_row_for_record


class TestExportMapping(unittest.TestCase):
    def test_export_headers_match_expected(self) -> None:
        base = ["Name", "Ext", "Type", "Folder", "Path", "Size", "Modified"]
        self.assertEqual(export_headers()[: len(base)], base)
        self.assertGreater(len(export_headers()), len(base))

    def test_export_row_shape_matches_headers(self) -> None:
        record = FileRecord(
            path=Path("C:/test/example.stl"),
            name="example.stl",
            extension=".stl",
            parent_folder="test",
            size_bytes=2048,
            modified_time=1713470580.0,
        )

        row = export_row_for_record(record)
        self.assertEqual(len(row), len(export_headers()))
        self.assertEqual(row[0], "example.stl")
        self.assertEqual(row[1], ".stl")


if __name__ == "__main__":
    unittest.main()
