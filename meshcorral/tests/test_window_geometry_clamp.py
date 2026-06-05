"""Unit tests for v0.1.1 window geometry clamp helper (pure QRect math)."""

from __future__ import annotations

import unittest

from PySide6.QtCore import QRect

from meshcorral.ui.main_window import clamp_rect_to_available


class TestWindowGeometryClamp(unittest.TestCase):
    def test_rect_too_tall_is_reduced_and_y_clamped(self) -> None:
        avail = QRect(0, 0, 1920, 1040)  # taskbar-safe area
        saved = QRect(100, -200, 1200, 3000)
        out = clamp_rect_to_available(saved, avail)
        self.assertLessEqual(out.height(), avail.height())
        self.assertGreaterEqual(out.top(), avail.top())
        self.assertLessEqual(out.bottom(), avail.bottom())

    def test_rect_below_screen_is_moved_up(self) -> None:
        avail = QRect(0, 0, 1920, 1040)
        saved = QRect(100, 5000, 800, 600)
        out = clamp_rect_to_available(saved, avail)
        self.assertGreaterEqual(out.top(), avail.top())
        self.assertLessEqual(out.bottom(), avail.bottom())

    def test_negative_y_is_clamped_to_top(self) -> None:
        avail = QRect(0, 0, 1920, 1040)
        saved = QRect(100, -999, 800, 600)
        out = clamp_rect_to_available(saved, avail)
        self.assertGreaterEqual(out.top(), avail.top())
        self.assertLessEqual(out.bottom(), avail.bottom())

    def test_stacked_monitors_negative_origin_available(self) -> None:
        # Simulate a monitor above primary: availableGeometry starts at negative y.
        avail = QRect(0, -1080, 1920, 1040)
        saved = QRect(50, -2000, 1200, 900)
        out = clamp_rect_to_available(saved, avail)
        self.assertGreaterEqual(out.top(), avail.top())
        self.assertLessEqual(out.bottom(), avail.bottom())

