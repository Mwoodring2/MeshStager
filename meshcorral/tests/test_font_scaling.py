"""Tests for teardown-safe relative font scaling.

The app stylesheet sets ``QWidget { font-size: 12px; }``, so widget fonts are
*pixel*-sized and ``QFont.pointSize()`` reports ``-1``. Feeding that back into
``setPointSize()`` produced Qt's ``QFont::setPointSize: Point size <= 0`` warning
(and a 1 pt title label). These tests pin the guarded behaviour.

The combo box tests cover the other direction: *Qt* reads a point size off a combo box
when the Windows 11 style builds its drop-down popup, so a pixel-only font made Qt call
``setPointSize(-1)`` once per process.
"""

from __future__ import annotations

import sys
import unittest

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QVBoxLayout

from meshcorral.ui.font_scaling import (
    DEFAULT_LOGICAL_DPI,
    MIN_PIXEL_SIZE,
    MIN_POINT_SIZE,
    ensure_combo_box_point_size,
    logical_dpi_for,
    normalize_combo_box_fonts,
    pixels_to_points,
    point_size_for_inherited_font,
    points_to_pixels,
    scale_font_points,
)
from meshcorral.ui.responsive_dialog import ResponsiveModalDialog
from meshcorral.ui.theme import build_app_stylesheet


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


class _AppStylesheetTestCase(unittest.TestCase):
    """Base case that applies the real application stylesheet (pixel font sizes)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def setUp(self) -> None:
        self._previous_stylesheet = self._app.styleSheet()
        self._app.setStyleSheet(build_app_stylesheet("dark"))

    def tearDown(self) -> None:
        self._app.setStyleSheet(self._previous_stylesheet)

    def _polished_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.addItems(["Balanced", "Fast", "Quality"])
        self.addCleanup(combo.deleteLater)
        combo.ensurePolished()
        return combo


class TestPixelsToPoints(unittest.TestCase):
    def test_round_trips_through_points_to_pixels(self) -> None:
        for dpi in (96.0, 120.0, 144.0):
            with self.subTest(dpi=dpi):
                points = pixels_to_points(12, dpi)
                self.assertGreater(points, 0.0)
                self.assertEqual(points_to_pixels(points, dpi), 12)

    def test_twelve_pixels_is_nine_points_at_96_dpi(self) -> None:
        self.assertAlmostEqual(pixels_to_points(12, 96.0), 9.0, places=6)

    def test_non_positive_dpi_falls_back_to_default(self) -> None:
        self.assertEqual(pixels_to_points(12, 0.0), pixels_to_points(12, DEFAULT_LOGICAL_DPI))


class TestPointSizeForInheritedFont(_AppStylesheetTestCase):
    def test_pixel_styled_widget_reports_equivalent_point_size(self) -> None:
        """A stylesheet px font must resolve to a positive, same-size point value."""
        combo = self._polished_combo()
        self.assertEqual(combo.font().pointSize(), -1)
        self.assertGreater(combo.font().pixelSize(), 0)

        points = point_size_for_inherited_font(combo)

        self.assertGreater(points, 0.0)
        expected = pixels_to_points(combo.font().pixelSize(), logical_dpi_for(combo))
        self.assertAlmostEqual(points, expected, places=6)

    def test_valid_point_font_is_returned_unchanged(self) -> None:
        label = QLabel("body")
        self.addCleanup(label.deleteLater)
        font = QFont("Segoe UI")
        font.setPointSizeF(11.0)
        label.setFont(font)
        self.assertAlmostEqual(point_size_for_inherited_font(label), 11.0, places=6)

    def test_never_returns_a_negative_size_to_hand_back_to_qt(self) -> None:
        """
        Whatever axis a widget font uses, the result is safe to give Qt.

        A font specified on neither axis cannot be built through the public API (Qt fills in
        the application size), so the app-font fallback stays defensive; the contract tested
        here is that ``-1`` never leaks out.
        """
        combo = self._polished_combo()
        label = QLabel("body")
        self.addCleanup(label.deleteLater)
        label.ensurePolished()

        for widget in (combo, label):
            with self.subTest(widget=type(widget).__name__):
                self.assertGreaterEqual(point_size_for_inherited_font(widget), 0.0)


class TestEnsureComboBoxPointSize(_AppStylesheetTestCase):
    def test_pixel_styled_combo_gains_a_valid_point_size(self) -> None:
        combo = self._polished_combo()
        self.assertEqual(combo.font().pointSize(), -1)

        self.assertTrue(ensure_combo_box_point_size(combo))

        self.assertGreater(combo.font().pointSizeF(), 0.0)

    def test_rendered_text_height_is_unchanged(self) -> None:
        """Restating px as pt must not resize any text on screen."""
        combo = self._polished_combo()
        before = QFontMetricsF(combo.font()).height()

        ensure_combo_box_point_size(combo)

        after = QFontMetricsF(combo.font()).height()
        self.assertAlmostEqual(before, after, delta=1.0)

    def test_already_point_sized_combo_is_left_alone(self) -> None:
        """Valid point-size behaviour must be preserved, not replaced."""
        combo = self._polished_combo()
        combo.setStyleSheet("font-size: 10pt;")
        combo.ensurePolished()
        self.assertAlmostEqual(combo.font().pointSizeF(), 10.0, places=6)

        self.assertFalse(ensure_combo_box_point_size(combo))

        self.assertEqual(combo.styleSheet(), "font-size: 10pt;")
        self.assertAlmostEqual(combo.font().pointSizeF(), 10.0, places=6)

    def test_second_call_is_a_no_op(self) -> None:
        combo = self._polished_combo()
        self.assertTrue(ensure_combo_box_point_size(combo))
        stylesheet_after_first = combo.styleSheet()

        self.assertFalse(ensure_combo_box_point_size(combo))

        self.assertEqual(combo.styleSheet(), stylesheet_after_first)
        self.assertEqual(stylesheet_after_first.count("font-size"), 1)

    def test_existing_widget_stylesheet_is_preserved(self) -> None:
        combo = self._polished_combo()
        combo.setStyleSheet("color: #ff0000;")
        combo.ensurePolished()

        self.assertTrue(ensure_combo_box_point_size(combo))

        self.assertIn("color: #ff0000;", combo.styleSheet())
        self.assertIn("pt;", combo.styleSheet())

    def test_normalize_walks_a_widget_tree(self) -> None:
        host = QLabel("host")
        self.addCleanup(host.deleteLater)
        layout = QVBoxLayout(host)
        for _ in range(3):
            combo = QComboBox()
            combo.addItems(["a", "b"])
            layout.addWidget(combo)
        host.ensurePolished()

        self.assertEqual(normalize_combo_box_fonts(host), 3)

        for combo in host.findChildren(QComboBox):
            self.assertGreater(combo.font().pointSizeF(), 0.0)

    def test_normalize_accepts_a_combo_box_as_the_root(self) -> None:
        combo = self._polished_combo()
        self.assertEqual(normalize_combo_box_fonts(combo), 1)
        self.assertGreater(combo.font().pointSizeF(), 0.0)


class TestComboPopupEmitsNoInvalidFontSize(_AppStylesheetTestCase):
    """
    Regression guard for ``QFont::setPointSize: Point size <= 0 (-1)``.

    Qt only emits this from the Windows 11 style, on the first drop-down of the process, so
    the assertion is "nothing invalid was emitted while we drove the offending path" rather
    than a strict reproduction. It fails if a combo box is ever popped up while its font
    carries no point size.
    """

    def setUp(self) -> None:
        super().setUp()
        self._messages: list[str] = []
        self._previous_handler = qInstallMessageHandler(self._collect)

    def tearDown(self) -> None:
        qInstallMessageHandler(self._previous_handler)
        super().tearDown()

    def _collect(self, mode: object, context: object, message: str) -> None:
        self._messages.append(str(message))

    def _font_size_warnings(self) -> list[str]:
        return [m for m in self._messages if "setPointSize" in m or "setPixelSize" in m]

    def _open_popup(self, combo: QComboBox) -> None:
        combo.show()
        self._app.processEvents()
        combo.showPopup()
        self._app.processEvents()
        combo.hidePopup()
        self._app.processEvents()
        combo.hide()

    def test_normalized_combo_popup_emits_no_font_size_warning(self) -> None:
        combo = self._polished_combo()
        ensure_combo_box_point_size(combo)

        self._open_popup(combo)

        self.assertEqual(self._font_size_warnings(), [])

    def test_combo_font_carries_a_point_size_when_the_popup_opens(self) -> None:
        """The precondition Qt needs: a positive point size before showPopup()."""
        combo = self._polished_combo()
        normalize_combo_box_fonts(combo)

        combo.show()
        self._app.processEvents()
        self.assertGreater(combo.font().pointSizeF(), 0.0)
        self._open_popup(combo)


class _ComboDialog(ResponsiveModalDialog):
    """Minimal responsive dialog with a combo box, for the show-path hook."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        self.combo.addItems(["Balanced", "Fast", "Quality"])
        layout.addWidget(self.combo)


class TestResponsiveDialogNormalizesCombos(_AppStylesheetTestCase):
    def test_dialog_show_gives_its_combo_a_valid_point_size(self) -> None:
        dialog = _ComboDialog()
        self.addCleanup(dialog.deleteLater)

        dialog.show()
        self._app.processEvents()

        self.assertGreater(dialog.combo.font().pointSizeF(), 0.0)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
