"""Prime v1.0 RC Sprint A5 — thumbnail visual consistency audit tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.badge_paint import build_health_badge_icon
from meshcorral.ui.thumbnails.placeholder_factory import build_format_card_icon
from meshcorral.ui.thumbnails.thumbnail_confidence import (
    ThumbConfidenceState,
    confidence_state_for,
)
from meshcorral.ui.thumbnails.thumbnail_style_rules import default_style_rules
from meshcorral.ui.thumbnails.unsupported_visuals import (
    UnsupportedVisualKind,
    identity_rgb_sum,
    resolve_unsupported_visual,
)
from meshcorral.ui.theme import build_app_stylesheet


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


def _record(name: str, ext: str = ".stl") -> FileRecord:
    path = Path(f"C:/work/{name}")
    return FileRecord(
        path=path,
        name=name,
        extension=ext,
        parent_folder="work",
        size_bytes=2048,
        modified_time=0.0,
    )


class TestFailureHierarchy(unittest.TestCase):
    """Deferred / unsupported / failed / corrupt must read as distinct families."""

    def test_deferred_calmer_than_failed_and_corrupt(self) -> None:
        deferred = resolve_unsupported_visual(".stl", deferred=True)
        failed = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.FAILED_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
        )
        corrupt = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.MISSING_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
        )
        self.assertEqual(deferred.kind, UnsupportedVisualKind.DEFERRED)
        self.assertEqual(failed.kind, UnsupportedVisualKind.FAILED)
        self.assertEqual(corrupt.kind, UnsupportedVisualKind.CORRUPT)
        dr, dg, db = deferred.base_rgb
        fr, fg, fb = failed.base_rgb
        cr, cg, cb = corrupt.base_rgb
        self.assertGreater(db, dr)
        self.assertGreater(fr, fg)
        self.assertGreater(cr, cg)
        self.assertGreater(fr, dr)
        self.assertGreater(cr, fr)
        self.assertLess(cg, fg)

    def test_unsupported_distinct_from_corrupt(self) -> None:
        unsupported = resolve_unsupported_visual(
            ".ma",
            health=ThumbHealth.UNSUPPORTED,
        )
        corrupt = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.MISSING_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
        )
        self.assertEqual(unsupported.kind, UnsupportedVisualKind.MA)
        self.assertEqual(corrupt.kind, UnsupportedVisualKind.CORRUPT)
        self.assertNotEqual(identity_rgb_sum(unsupported), identity_rgb_sum(corrupt))

    def test_failed_confidence_is_failure_family(self) -> None:
        state = confidence_state_for(
            ThumbVisualState.FAILED,
            health=ThumbHealth.FAILED_THUMBNAIL,
        )
        self.assertEqual(state, ThumbConfidenceState.FAILED)
        self.assertTrue(state.is_failure_family())

    def test_corrupt_confidence_is_failure_family(self) -> None:
        state = confidence_state_for(ThumbVisualState.FAILED)
        self.assertEqual(state, ThumbConfidenceState.CORRUPT)
        self.assertTrue(state.is_failure_family())

    def test_deferred_confidence_informational(self) -> None:
        state = confidence_state_for(
            ThumbVisualState.PLACEHOLDER,
            deferred=True,
        )
        self.assertEqual(state, ThumbConfidenceState.DEFERRED)
        self.assertTrue(state.is_informational())
        self.assertIn("deferred", state.card_subtitle().lower())


class TestBadgeTokens(unittest.TestCase):
    """Gallery/table overlay badges share one token system."""

    def test_ready_smaller_or_equal_error_badge(self) -> None:
        rules = default_style_rules()
        dark = rules.badge_tokens("dark")
        light = rules.badge_tokens("light")
        self.assertLessEqual(dark.ready_side_px, dark.error_side_px)
        self.assertEqual(dark.ready_side_px, light.ready_side_px)
        self.assertEqual(dark.corner_radius_px, light.corner_radius_px)

    def test_health_badge_icons_non_null(self) -> None:
        _qapp()
        for health in ThumbHealth:
            for mode in ("dark", "light"):
                icon = build_health_badge_icon(health, theme_mode=mode)
                pm = icon.pixmap(20, 20)
                self.assertFalse(pm.isNull(), f"{health} {mode}")


class TestPlaceholderCards(unittest.TestCase):
    """Format cards expose expected title/subtitle copy."""

    def test_deferred_card_copy(self) -> None:
        _qapp()
        icon = build_format_card_icon(
            _record("part.stl"),
            visual=ThumbVisualState.PLACEHOLDER,
            health=ThumbHealth.PENDING,
            px=96,
            deferred=True,
        )
        self.assertFalse(icon.isNull())
        state = confidence_state_for(
            ThumbVisualState.PLACEHOLDER,
            deferred=True,
        )
        self.assertEqual(state.card_title(), "Deferred Preview")
        self.assertIn("Deferred", state.card_subtitle())

    def test_long_filename_card_does_not_crash(self) -> None:
        _qapp()
        long_name = "a" * 240 + "_very_long_mesh_name.stl"
        icon = build_format_card_icon(
            _record(long_name),
            visual=ThumbVisualState.PLACEHOLDER,
            health=ThumbHealth.PENDING,
            px=160,
            deferred=True,
            theme_mode="light",
        )
        pm = icon.pixmap(160, 160)
        self.assertFalse(pm.isNull())
        self.assertEqual(pm.width(), 160)
        self.assertEqual(pm.height(), 160)


class TestThemeParity(unittest.TestCase):
    """Stylesheets expose preview/thumbnail state object names in both themes."""

    def test_stylesheet_includes_thumbnail_state_labels(self) -> None:
        for mode in ("dark", "light"):
            css = build_app_stylesheet(theme_mode=mode)
            self.assertIn("PreviewThumbState", css)
            self.assertIn("PreviewThumbSubline", css)
            self.assertIn("InspectorBadge", css)

    def test_confidence_tint_deferred_calmer_than_failed(self) -> None:
        rules = default_style_rules()
        base = (72, 108, 96)
        deferred = rules.confidence_tint_rgb(
            base,
            confidence=ThumbConfidenceState.DEFERRED,
        )
        failed = rules.confidence_tint_rgb(
            base,
            confidence=ThumbConfidenceState.FAILED,
        )
        self.assertGreater(failed[0], deferred[0])
        self.assertLess(
            rules.card_background_alpha_for(ThumbConfidenceState.DEFERRED),
            rules.card_background_alpha_for(ThumbConfidenceState.FAILED),
        )


class TestFramingHelpers(unittest.TestCase):
    """Decoded thumbs fit square cells with padding (display-only)."""

    def test_frame_pixmap_preserves_square_canvas(self) -> None:
        _qapp()
        from PySide6.QtGui import QPixmap

        rules = default_style_rules()
        src = QPixmap(200, 80)
        src.fill()
        framed = rules.frame_pixmap_in_square(src, side_px=96)
        self.assertEqual(framed.width(), 96)
        self.assertEqual(framed.height(), 96)


if __name__ == "__main__":
    unittest.main()
