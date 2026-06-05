"""DPI/layout constant sanity checks (Prime v1.0 RC A4)."""

from __future__ import annotations

import unittest

from meshcorral.ui import layout_constants as lc


class TestDpiLayoutConstants(unittest.TestCase):
    """Constants stay within ranges that work at 100%–150% scaling."""

    def test_right_panel_widths(self) -> None:
        self.assertLessEqual(lc.MIN_RIGHT_PANEL_WIDTH, lc.DEFAULT_RIGHT_PANEL_WIDTH)
        self.assertLessEqual(lc.DEFAULT_RIGHT_PANEL_WIDTH, lc.MAX_RIGHT_PANEL_WIDTH)
        self.assertGreaterEqual(lc.MIN_RIGHT_PANEL_WIDTH, 280)
        self.assertLessEqual(lc.MAX_RIGHT_PANEL_WIDTH, 640)

    def test_inspector_fits_narrow_right_panel(self) -> None:
        """Tab min width × typical tab count should fit default right panel."""
        tab_count = 4
        tabs_width = lc.MIN_INSPECTOR_TAB_WIDTH * tab_count
        self.assertLess(tabs_width, lc.DEFAULT_RIGHT_PANEL_WIDTH)

    def test_control_and_dialog_sizes(self) -> None:
        self.assertGreaterEqual(lc.CONTROL_HEIGHT, 28)
        self.assertLessEqual(lc.CONTROL_HEIGHT, 40)
        self.assertGreaterEqual(lc.DIALOG_MIN_WIDTH, 400)
        self.assertGreaterEqual(lc.SETTINGS_DIALOG_MIN_WIDTH, lc.DIALOG_MIN_WIDTH)
        self.assertGreaterEqual(lc.LARGE_FOLDER_DIALOG_MIN_WIDTH, lc.DIALOG_MIN_WIDTH)

    def test_preview_minimum_heights(self) -> None:
        self.assertGreaterEqual(lc.INSPECTOR_PREVIEW_MIN_HEIGHT_3D, 96)
        self.assertGreaterEqual(lc.INSPECTOR_PREVIEW_MIN_HEIGHT_IMAGES, lc.INSPECTOR_PREVIEW_MIN_HEIGHT_3D)

    def test_inspector_tab_min_height_sane(self) -> None:
        self.assertGreaterEqual(lc.INSPECTOR_TAB_MIN_HEIGHT, 24)
        self.assertLessEqual(lc.INSPECTOR_TAB_MIN_HEIGHT, 36)
        self.assertGreaterEqual(lc.SECTION_GAP, 8)
        self.assertGreaterEqual(lc.PANEL_GAP, 4)


if __name__ == "__main__":
    unittest.main()
