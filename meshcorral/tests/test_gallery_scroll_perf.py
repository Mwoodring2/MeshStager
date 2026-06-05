"""RC3 gallery scroll performance: cache, layout generation, selection debounce."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.gallery_list_model import GalleryListModel
from meshcorral.ui.gallery_perf_constants import (
    gallery_max_visible_build,
    gallery_scroll_debounce_ms,
)
from meshcorral.ui.gallery_scaled_pixmap_cache import (
    GalleryScaledPixmapCache,
    gallery_scaled_pixmap_key,
)
from meshcorral.ui.thumbnail_controller import ThumbnailViewController


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


class TestGalleryScaledPixmapCache(unittest.TestCase):
    """Scaled thumbnail cache keyed by path fingerprint and gallery size."""

    def test_cache_hit_after_put(self) -> None:
        _qapp()
        cache = GalleryScaledPixmapCache(max_items=8)
        key = gallery_scaled_pixmap_key(
            "c:/a.png",
            96,
            size_bytes=100,
            modified_time=1.5,
        )
        pm = QPixmap(32, 32)
        pm.fill()
        cache.put(key, pm)
        hit = cache.get(key)
        if hit is None:
            self.fail("expected cache hit")
        self.assertFalse(hit.isNull())
        stats = cache.stats()
        self.assertGreaterEqual(stats["hits"], 1)

    def test_fingerprint_change_is_miss(self) -> None:
        _qapp()
        cache = GalleryScaledPixmapCache(max_items=8)
        pm = QPixmap(16, 16)
        pm.fill()
        k1 = gallery_scaled_pixmap_key("c:/b.jpg", 48, size_bytes=1, modified_time=0.0)
        cache.put(k1, pm)
        k2 = gallery_scaled_pixmap_key("c:/b.jpg", 48, size_bytes=2, modified_time=0.0)
        self.assertIsNone(cache.get(k2))


class TestGalleryLayoutGeneration(unittest.TestCase):
    """Full gallery rebuild is tied to set_records, not per-row emit."""

    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    def setUp(self) -> None:
        self._thumb = ThumbnailViewController()
        self._model = GalleryListModel(self._thumb)

    def test_set_records_increments_layout_generation(self) -> None:
        record = FileRecord(
            path=Path("C:/t/a.stl"),
            name="a.stl",
            extension=".stl",
            parent_folder="t",
            size_bytes=1,
            modified_time=0.0,
        )
        self.assertEqual(self._model.layout_generation, 0)
        self._model.set_records([record])
        self.assertEqual(self._model.layout_generation, 1)
        self._model.set_records([record])
        self.assertEqual(self._model.layout_generation, 2)

    def test_emit_items_does_not_increment_layout_generation(self) -> None:
        record = FileRecord(
            path=Path("C:/t/a.stl"),
            name="a.stl",
            extension=".stl",
            parent_folder="t",
            size_bytes=1,
            modified_time=0.0,
        )
        self._model.set_records([record])
        gen = self._model.layout_generation
        self._model.emit_items_for_path_key("c:/t/a.stl")
        self.assertEqual(self._model.layout_generation, gen)

    def test_decoration_role_not_loaded_in_model(self) -> None:
        """Scroll repaint should not pull DecorationRole through decode path."""
        record = FileRecord(
            path=Path("C:/t/x.png"),
            name="x.png",
            extension=".png",
            parent_folder="t",
            size_bytes=1,
            modified_time=0.0,
        )
        self._model.set_records([record])
        ix = self._model.index(0)
        deco = ix.data(Qt.ItemDataRole.DecorationRole)
        self.assertIsNone(deco)


class TestGalleryPerfConstants(unittest.TestCase):
    def test_default_debounce_ms(self) -> None:
        self.assertEqual(gallery_scroll_debounce_ms(), 75)

    def test_default_max_visible_build(self) -> None:
        self.assertEqual(gallery_max_visible_build(), 100)


class TestSelectionInspectorDebounce(unittest.TestCase):
    def test_selection_change_schedules_debounced_inspector(self) -> None:
        from meshcorral.ui.main_window import MainWindow

        window = MagicMock(spec=MainWindow)
        window._shutting_down = False
        timer = MagicMock()
        window._selection_inspector_debounce = timer

        with patch(
            "meshcorral.ui.main_window.gallery_scroll_debounce_ms",
            return_value=50,
        ):
            from meshcorral.ui.main_window import MainWindow as MW

            MW._on_file_selection_changed(window)
            window._update_ui_state.assert_called_once_with(refresh_inspector=False)
            timer.stop.assert_called_once()
            timer.start.assert_called_once_with(50)


class TestThumbnailGalleryPaintCache(unittest.TestCase):
    def test_gallery_paint_pixmap_uses_scaled_cache(self) -> None:
        _qapp()
        ctrl = ThumbnailViewController()
        record = FileRecord(
            path=Path("C:/t/c.png"),
            name="c.png",
            extension=".png",
            parent_folder="t",
            size_bytes=10,
            modified_time=1.0,
        )
        norm = _norm_path_key(record.path)
        scaled_key = gallery_scaled_pixmap_key(
            norm,
            ctrl.display_pixel_size(),
            size_bytes=record.size_bytes,
            modified_time=record.modified_time,
        )
        pm = QPixmap(24, 24)
        pm.fill()
        ctrl._gallery_scaled.put(scaled_key, pm)
        out = ctrl.gallery_paint_pixmap(record, ctrl.display_pixel_size())
        self.assertFalse(out.isNull())
        stats = ctrl.gallery_scaled_cache_stats()
        self.assertGreaterEqual(stats["hits"], 1)


if __name__ == "__main__":
    unittest.main()
