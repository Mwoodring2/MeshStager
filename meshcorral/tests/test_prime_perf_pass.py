"""Prime Performance Pass v0.3 — Phase 1 tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from meshcorral.app.bridge.visible_thumb_queue import (
    expand_row_indices,
    is_raster_thumbnail_extension,
    prioritize_visible_records,
    select_auto_thumbnail_candidates,
)
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import (
    THUMB_FILTER_ALL,
    THUMB_FILTER_MISSING,
    ThumbHealth,
    thumb_health_matches_filter,
)
from meshcorral.services.lazy_thumb_health import LazyThumbHealthResolver
from meshcorral.services.settings_service import SettingsService


def _rec(path: str, ext: str = ".stl") -> FileRecord:
    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=ext,
        parent_folder="folder",
        size_bytes=1,
        modified_time=0.0,
    )


class TestVisibleThumbQueue(unittest.TestCase):
    def test_expand_margin(self) -> None:
        rows = expand_row_indices([5], 20, margin=2)
        self.assertEqual(rows, [5, 4, 6, 3, 7])

    def test_prioritize_visible_first(self) -> None:
        records = [_rec(f"C:/a/{i}.stl") for i in range(10)]
        ordered = prioritize_visible_records(records, [8, 9], margin=0)
        self.assertEqual([r.name for r in ordered], ["8.stl", "9.stl"])

    def test_select_candidates_respects_cap(self) -> None:
        records = [_rec(f"C:/a/{i}.stl") for i in range(10)]

        def _never_has(_r: FileRecord) -> bool:
            return False

        picked = select_auto_thumbnail_candidates(
            records,
            has_thumbnail=_never_has,
            cap=3,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        self.assertEqual(len(picked), 3)
        self.assertEqual(picked[0].name, "0.stl")


class TestLazyThumbHealth(unittest.TestCase):
    def test_pending_until_resolved(self) -> None:
        calls: list[str] = []

        def _resolve(record: FileRecord) -> ThumbHealth:
            calls.append(record.name)
            return ThumbHealth.MISSING_THUMBNAIL

        lazy = LazyThumbHealthResolver(_resolve)
        lazy.set_lazy_enabled(True)
        rec = _rec("C:/a/mesh.stl")
        self.assertEqual(lazy.thumb_health(rec), ThumbHealth.PENDING)
        self.assertEqual(calls, [])
        self.assertEqual(lazy.resolve(rec), ThumbHealth.MISSING_THUMBNAIL)
        self.assertEqual(lazy.thumb_health(rec), ThumbHealth.MISSING_THUMBNAIL)
        self.assertEqual(calls, ["mesh.stl"])

    def test_pending_only_matches_all_filter(self) -> None:
        self.assertTrue(thumb_health_matches_filter(THUMB_FILTER_ALL, ThumbHealth.PENDING))
        self.assertFalse(
            thumb_health_matches_filter(THUMB_FILTER_MISSING, ThumbHealth.PENDING)
        )

    def test_no_full_resolve_on_many_records(self) -> None:
        """Lazy mode should not call the resolver until rows are resolved."""
        resolve_count = 0

        def _resolve(_record: FileRecord) -> ThumbHealth:
            nonlocal resolve_count
            resolve_count += 1
            return ThumbHealth.UNSUPPORTED

        lazy = LazyThumbHealthResolver(_resolve)
        lazy.set_lazy_enabled(True)
        records = [_rec(f"C:/a/{i}.png", ".png") for i in range(500)]
        for record in records:
            _ = lazy.thumb_health(record)
        self.assertEqual(resolve_count, 0)
        lazy.resolve_many(records[:3])
        self.assertEqual(resolve_count, 3)


class TestAutoThumbCapIntegration(unittest.TestCase):
    def test_network_scan_uses_25_cap(self) -> None:
        from meshcorral.utils.path_perf import effective_auto_thumbnail_cap

        cap = effective_auto_thumbnail_cap(
            Path(r"\\server\share"),
            400,
            12.0,
            SettingsService.CAP_AUTO_THUMB_UNLIMITED,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        self.assertEqual(cap, 25)

    def test_visible_first_queue_order(self) -> None:
        records = [_rec(f"C:/a/{i}.stl") for i in range(5)]
        visible = prioritize_visible_records(records, [4], margin=0)
        with mock.patch(
            "meshcorral.app.bridge.visible_thumb_queue.is_auto_thumbnail_extension",
            return_value=True,
        ):
            picked = select_auto_thumbnail_candidates(
                visible,
                has_thumbnail=lambda _r: False,
                cap=1,
                unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
            )
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0].name, "4.stl")

    def test_raster_extension_detected(self) -> None:
        rec = _rec("C:/a/photo.psd", ".psd")
        self.assertTrue(is_raster_thumbnail_extension(rec))


if __name__ == "__main__":
    unittest.main()
