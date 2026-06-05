"""Tests for :class:`~meshcorral.models.file_record.FileRecord` name search cache."""

from __future__ import annotations

import unittest
from pathlib import Path

from meshcorral.models.file_record import FileRecord


class TestFileRecordNameLower(unittest.TestCase):
    """``name_lower`` matches ``name.lower()`` for filter hot paths."""

    def test_name_lower_follows_name(self) -> None:
        rec = FileRecord(
            path=Path("C:/x/Rock.Mesh.obj"),
            name="Rock.Mesh.obj",
            extension=".obj",
            parent_folder="x",
            size_bytes=1,
            modified_time=0.0,
        )
        self.assertEqual(rec.name_lower, "rock.mesh.obj")


if __name__ == "__main__":
    unittest.main()
