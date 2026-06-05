"""Tests for in-memory filtering (intersection semantics)."""

from __future__ import annotations

import unittest
from pathlib import Path

from meshcorral.app.config import ASSET_MODE_IMAGES
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import (
    THUMB_FILTER_MISSING,
    THUMB_FILTER_UNSUPPORTED,
    ThumbHealth,
)
from meshcorral.services.search_service import filter_records


def _rec(name: str, ext: str, folder: str) -> FileRecord:
    p = Path(f"C:/x/{folder}/{name}")
    return FileRecord(
        path=p,
        name=name,
        extension=ext,
        parent_folder=folder,
        size_bytes=1,
        modified_time=0.0,
    )


class TestFilterRecords(unittest.TestCase):
    """Filters combine as intersection; ``_all_records`` style list is not mutated."""

    def test_combined_filters_intersect(self) -> None:
        rows = [
            _rec("a.stl", ".stl", "A"),
            _rec("b.obj", ".obj", "A"),
            _rec("c.stl", ".stl", "B"),
        ]
        out = filter_records(
            rows,
            search_text="",
            extension_filter=".stl",
            folder_filter="A",
            category_filter="All",
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].name, "a.stl")

    def test_text_filter_with_category(self) -> None:
        rows = [_rec("foo.stl", ".stl", "A"), _rec("bar.stl", ".stl", "A")]
        out = filter_records(
            rows,
            search_text="bar",
            extension_filter="All",
            folder_filter="All Folders",
            category_filter="Geometry",
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].name, "bar.stl")

    def test_filter_with_image_asset_mode(self) -> None:
        """Image mode 'All' only allows SUPPORTED_IMAGE_EXTENSIONS in category filter."""
        rows = [
            _rec("a.png", ".png", "A"),
            _rec("b.stl", ".stl", "A"),
        ]
        out = filter_records(
            rows,
            asset_mode=ASSET_MODE_IMAGES,
            category_filter="All",
        )
        self.assertEqual([r.name for r in out], ["a.png"])

    def test_thumb_health_filter(self) -> None:
        rows = [_rec("a.stl", ".stl", "A"), _rec("b.blend", ".blend", "A")]

        def fake_health(record: FileRecord) -> ThumbHealth:
            if record.extension == ".stl":
                return ThumbHealth.MISSING_THUMBNAIL
            return ThumbHealth.UNSUPPORTED

        missing = filter_records(
            rows,
            thumb_health_filter=THUMB_FILTER_MISSING,
            thumb_health_for=fake_health,
        )
        self.assertEqual([r.name for r in missing], ["a.stl"])
        unsupported = filter_records(
            rows,
            thumb_health_filter=THUMB_FILTER_UNSUPPORTED,
            thumb_health_for=fake_health,
        )
        self.assertEqual([r.name for r in unsupported], ["b.blend"])
