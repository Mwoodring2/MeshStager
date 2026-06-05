"""Prime v1.0 RC A5.2 PR2 — badge rhythm and shared metrics."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.badge_paint import build_badge_icon, build_health_badge_icon
from meshcorral.ui.thumbnails.badge_styles import (
    BADGE_CORNER_RADIUS,
    BADGE_MARGIN,
    BADGE_OPACITY,
    BADGE_PADDING,
    BADGE_SELECTED_OPACITY,
    BADGE_SIZE_MEDIUM,
    BADGE_SIZE_SMALL,
    BadgeStyleKind,
    badge_theme_dark,
    badge_theme_light,
    gallery_badge_rect,
    resolve_badge_style_kind,
)
from meshcorral.ui.thumbnails.thumbnail_style_rules import default_style_rules


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


class TestBadgeMetrics(unittest.TestCase):
    def test_shared_metrics_sane(self) -> None:
        self.assertLessEqual(BADGE_SIZE_SMALL, BADGE_SIZE_MEDIUM)
        self.assertGreaterEqual(BADGE_PADDING, 1)
        self.assertGreaterEqual(BADGE_MARGIN, 2)
        self.assertGreater(BADGE_SELECTED_OPACITY, BADGE_OPACITY)
        self.assertGreaterEqual(BADGE_CORNER_RADIUS, 2)

    def test_gallery_badge_rect_inside_thumb(self) -> None:
        bx, by = gallery_badge_rect(10, 20, 96, 96, BADGE_SIZE_MEDIUM, margin=BADGE_MARGIN)
        self.assertGreaterEqual(bx, 10)
        self.assertGreaterEqual(by, 20)
        self.assertLessEqual(bx + BADGE_SIZE_MEDIUM, 10 + 96)
        self.assertLessEqual(by + BADGE_SIZE_MEDIUM, 20 + 96)


class TestBadgeStyleHierarchy(unittest.TestCase):
    def test_ready_smaller_than_warning_badges(self) -> None:
        dark = badge_theme_dark()
        self.assertLess(dark.ready.side_px, dark.failed.side_px)
        self.assertEqual(dark.ready.side_px, BADGE_SIZE_SMALL)
        self.assertEqual(dark.failed.side_px, BADGE_SIZE_MEDIUM)

    def test_failed_corrupt_timeout_distinct_colors(self) -> None:
        dark = badge_theme_dark()
        self.assertNotEqual(dark.failed.fg_rgb, dark.corrupt.fg_rgb)
        self.assertNotEqual(dark.failed.fg_rgb, dark.timeout.fg_rgb)
        self.assertNotEqual(dark.corrupt.fg_rgb, dark.timeout.fg_rgb)

    def test_failed_corrupt_share_geometry(self) -> None:
        dark = badge_theme_dark()
        self.assertEqual(dark.failed.side_px, dark.corrupt.side_px)
        self.assertEqual(dark.failed.side_px, dark.timeout.side_px)

    def test_deferred_calmer_than_failed(self) -> None:
        dark = badge_theme_dark()
        self.assertEqual(dark.deferred.kind, BadgeStyleKind.DEFERRED)
        self.assertEqual(dark.failed.kind, BadgeStyleKind.FAILED)
        self.assertNotEqual(dark.deferred.fg_rgb, dark.failed.fg_rgb)
        self.assertNotEqual(dark.deferred.fill_rgb, dark.failed.fill_rgb)

    def test_resolve_timeout_vs_failed(self) -> None:
        failed = resolve_badge_style_kind(
            health=ThumbHealth.FAILED_THUMBNAIL,
            bridge_error_message="job timed out",
        )
        generic = resolve_badge_style_kind(
            health=ThumbHealth.FAILED_THUMBNAIL,
            bridge_error_message="export failed",
        )
        self.assertEqual(failed, BadgeStyleKind.TIMEOUT)
        self.assertEqual(generic, BadgeStyleKind.FAILED)

    def test_progress_not_error(self) -> None:
        kind = resolve_badge_style_kind(
            health=ThumbHealth.PENDING,
            generating=True,
        )
        self.assertEqual(kind, BadgeStyleKind.PROGRESS)


class TestBadgeIcons(unittest.TestCase):
    def test_icons_build_for_all_kinds(self) -> None:
        _qapp()
        for kind in BadgeStyleKind:
            for theme in (badge_theme_dark, badge_theme_light):
                icon = build_badge_icon(kind, theme_mode="dark" if theme == badge_theme_dark else "light")
                pm = icon.pixmap(BADGE_SIZE_MEDIUM, BADGE_SIZE_MEDIUM)
                self.assertFalse(pm.isNull(), f"{kind}")

    def test_health_ready_icon_small(self) -> None:
        _qapp()
        icon = build_health_badge_icon(ThumbHealth.HAS_THUMBNAIL, theme_mode="dark")
        pm = icon.pixmap(BADGE_SIZE_SMALL, BADGE_SIZE_SMALL)
        self.assertFalse(pm.isNull())
        self.assertLessEqual(pm.width(), BADGE_SIZE_MEDIUM)

    def test_tokens_match_theme(self) -> None:
        tokens = default_style_rules().badge_tokens("dark")
        self.assertEqual(tokens.ready_side_px, BADGE_SIZE_SMALL)
        self.assertEqual(tokens.info_side_px, BADGE_SIZE_MEDIUM)


if __name__ == "__main__":
    unittest.main()
