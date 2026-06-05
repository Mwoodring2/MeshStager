"""Tests for :mod:`meshcorral.models.thumb_health` classification helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import (
    THUMB_FILTER_ALL,
    THUMB_FILTER_HAS,
    ThumbHealth,
    classify_thumb_health,
    thumb_health_matches_filter,
)


def _record(path: str, ext: str) -> FileRecord:
    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=ext,
        parent_folder=p.parent.name if p.parent != p else "",
        size_bytes=1,
        modified_time=0.0,
    )


class TestClassifyThumbHealth(unittest.TestCase):
    """Ordering: resolved thumbnail, then failure, then mesh extension rules."""

    def test_thumbnail_wins_over_failure_record(self) -> None:
        rec = _record("C:/m/a.stl", ".stl")
        h = classify_thumb_health(
            has_resolved_thumbnail=True,
            has_recorded_failure=True,
            record=rec,
        )
        self.assertEqual(h, ThumbHealth.HAS_THUMBNAIL)

    def test_missing_mesh_when_no_thumb_no_failure(self) -> None:
        rec = _record("C:/m/a.stl", ".stl")
        h = classify_thumb_health(
            has_resolved_thumbnail=False,
            has_recorded_failure=False,
            record=rec,
        )
        self.assertEqual(h, ThumbHealth.MISSING_THUMBNAIL)

    def test_unsupported_extension(self) -> None:
        rec = _record("C:/m/t.png", ".png")
        h = classify_thumb_health(
            has_resolved_thumbnail=False,
            has_recorded_failure=False,
            record=rec,
        )
        self.assertEqual(h, ThumbHealth.UNSUPPORTED)

    def test_thumb_health_matches_filter_all(self) -> None:
        self.assertTrue(
            thumb_health_matches_filter(THUMB_FILTER_ALL, ThumbHealth.MISSING_THUMBNAIL)
        )
        self.assertTrue(thumb_health_matches_filter(THUMB_FILTER_ALL, ThumbHealth.PENDING))
        self.assertFalse(thumb_health_matches_filter(THUMB_FILTER_HAS, ThumbHealth.PENDING))
        self.assertTrue(
            thumb_health_matches_filter(THUMB_FILTER_HAS, ThumbHealth.HAS_THUMBNAIL)
        )
        self.assertFalse(
            thumb_health_matches_filter(THUMB_FILTER_HAS, ThumbHealth.MISSING_THUMBNAIL)
        )


if __name__ == "__main__":
    unittest.main()
