"""Prime v1.0 RC A5.2 — thumbnail paint stability (idle churn reduction)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.app.config import SUPPORTED_IMAGE_EXTENSIONS
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.services.lazy_thumb_health import LazyThumbHealthResolver
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.thumbnail_controller import ThumbnailViewController


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


def _record(name: str = "part.stl", ext: str = ".stl") -> FileRecord:
    path = Path(f"C:/work/{name}")
    return FileRecord(
        path=path,
        name=name,
        extension=ext,
        parent_folder="work",
        size_bytes=1024,
        modified_time=0.0,
    )


class TestLazyHealthEmitDedup(unittest.TestCase):
    def test_resolve_many_changed_skips_unchanged(self) -> None:
        calls = {"n": 0}

        def resolve(_rec: FileRecord) -> ThumbHealth:
            calls["n"] += 1
            return ThumbHealth.PENDING

        resolver = LazyThumbHealthResolver(resolve)
        resolver.set_lazy_enabled(True)
        rec = _record()
        first = resolver.resolve_many_changed([rec])
        second = resolver.resolve_many_changed([rec])
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(calls["n"], 2)

    def test_resolve_many_changed_emits_on_transition(self) -> None:
        state = {"health": ThumbHealth.PENDING}

        def resolve(_rec: FileRecord) -> ThumbHealth:
            return state["health"]

        resolver = LazyThumbHealthResolver(resolve)
        resolver.set_lazy_enabled(True)
        rec = _record()
        resolver.resolve_many_changed([rec])
        state["health"] = ThumbHealth.HAS_THUMBNAIL
        changed = resolver.resolve_many_changed([rec])
        self.assertEqual(len(changed), 1)


class TestGalleryDecorationCache(unittest.TestCase):
    def test_second_decoration_paint_uses_cache(self) -> None:
        _qapp()
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        rec = _record("img.png", ".png")
        ext = rec.extension.lower().strip()
        if ext not in SUPPORTED_IMAGE_EXTENSIONS:
            self.skipTest("unexpected extension")
        ctrl._ready_cache.mark_ready(rec.path, None)
        diag = ctrl.paint_diagnostics()
        diag.reset()
        ctrl.decoration_for(rec)
        first_placeholders = diag.placeholder_paints
        first_deco_hits = diag.decoration_cache_hits
        ctrl.decoration_for(rec)
        self.assertGreaterEqual(diag.decoration_cache_hits, first_deco_hits + 1)
        self.assertEqual(diag.placeholder_paints, first_placeholders)


class TestPlaceholderPaintAccounting(unittest.TestCase):
    def test_card_icon_cache_avoids_placeholder_counter(self) -> None:
        _qapp()
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        rec = _record()
        diag = ctrl.paint_diagnostics()
        diag.reset()
        ctrl._placeholder_icon(rec, purpose="gallery", px=96)
        first = diag.placeholder_paints
        ctrl._placeholder_icon(rec, purpose="gallery", px=96)
        self.assertEqual(diag.placeholder_paints, first)


if __name__ == "__main__":
    unittest.main()
