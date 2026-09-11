"""Tests for teardown-safe relative font scaling.

The app stylesheet sets ``QWidget { font-size: 12px; }``, so widget fonts are
*pixel*-sized and ``QFont.pointSize()`` reports ``-1``. Feeding that back into
``setPointSize()`` produced Qt's ``QFont::setPointSize: Point size <= 0`` warning
(and a 1 pt title label). These tests pin the guarded behaviour.
"""

from __future__ import annotations

import sys
import unittest

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel

from meshcorral.ui.font_scaling import (
    DEFAULT_LOGICAL_DPI,
    MIN_PIXEL_SIZE,
    MIN_POINT_SIZE,
    logical_dpi_for,
    points_to_pixels,
    scale_font_points,
)


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication(sys.argv)
    return inst  # type: ignore[return-value]


class TestScaleFontPoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_point_sized_font_scales_in_points(self) -> None:
        base = QFont("Segoe UI")
        base.setPointSizeF(11.0)
        scaled = scale_font_points(base, 2.0)
        self.assertAlmostEqual(scaled.pointSizeF(), 13.0, places=3)
        self.assertEqual(scaled.pixelSize(), -1)

    def test_pixel_sized_font_scales_in_pixels_and_never_sets_point_size(self) -> None:
        """The ``-1`` point size of a stylesheet px font must never reach Qt."""
        base = QFont("Segoe UI")
        base.setPixelSize(12)
        self.assertEqual(base.pointSize(), -1)

        scaled = scale_font_points(base, 2.0)

        self.assertEqual(scaled.pointSize(), -1)
        self.assertGreater(scaled.pixelSize(), 12)
        self.assertEqual(scaled.pixelSize(), 12 + points_to_pixels(2.0, logical_dpi_for()))

    def test_pixel_font_never_shrinks_below_floor(self) -> None:
        base = QFont("Segoe UI")
        base.setPixelSize(7)
        scaled = scale_font_points(base, -40.0)
        self.assertGreaterEqual(scaled.pixelSize(), MIN_PIXEL_SIZE)

    def test_point_font_never_shrinks_below_floor(self) -> None:
        base = QFont("Segoe UI")
        base.setPointSizeF(8.0)
        scaled = scale_font_points(base, -40.0)
        self.assertGreaterEqual(scaled.pointSizeF(), MIN_POINT_SIZE)

    def test_original_font_is_not_mutated(self) -> None:
        base = QFont("Segoe UI")
        base.setPointSizeF(10.0)
        scale_font_points(base, 5.0)
        self.assertAlmostEqual(base.pointSizeF(), 10.0, places=3)

    def test_stylesheet_styled_label_keeps_a_usable_size(self) -> None:
        """Regression: a px-styled label used to collapse to a 1 pt title."""
        label = QLabel("Large Folder / Server Scan Detected")
        label.setStyleSheet("font-size: 12px;")
        label.ensurePolished()

        scaled = scale_font_points(label.font(), 2.0, widget=label)

        self.assertTrue(scaled.pixelSize() >= MIN_PIXEL_SIZE or scaled.pointSizeF() > 1.0)
        self.assertNotEqual(scaled.pointSize(), 1)


class TestDpiHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_points_to_pixels_at_96_dpi(self) -> None:
        self.assertEqual(points_to_pixels(12.0, 96.0), 16)

    def test_points_to_pixels_rejects_non_positive_dpi(self) -> None:
        self.assertEqual(points_to_pixels(12.0, 0.0), points_to_pixels(12.0, DEFAULT_LOGICAL_DPI))

    def test_logical_dpi_is_positive(self) -> None:
        self.assertGreater(logical_dpi_for(), 0.0)


class TestLargeFolderDialogTitleFont(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_title_font_is_larger_than_body_and_never_one_point(self) -> None:
        body = QLabel("body")
        body.setStyleSheet("font-size: 12px;")
        body.ensurePolished()
        title_font = scale_font_points(body.font(), 2.0, widget=body)

        if body.font().pixelSize() > 0:
            self.assertGreater(title_font.pixelSize(), body.font().pixelSize())
        else:
            self.assertGreater(title_font.pointSizeF(), body.font().pointSizeF())


if __name__ == "__main__":
    unittest.main()
