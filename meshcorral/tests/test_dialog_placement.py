"""Tests for modal dialog centering and responsive layout (RC3 QoL)."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

from pathlib import Path

from PySide6.QtCore import QSettings, QRect
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from meshcorral.models.move_plan import MovePlan
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.dialog_placement import (
    SETTINGS_DIALOG_HORIZONTAL_MARGIN,
    SETTINGS_DIALOG_VERTICAL_MARGIN,
    available_geometry_for_widget,
    center_dialog_over_parent,
    clamp_dialog_size_to_screen,
    clamp_frame_rect_to_available,
    dialog_frame_extra,
    screen_for_dialog,
)
from meshcorral.ui.dialogs import MovePreviewDialog
from meshcorral.ui.large_folder_warning_dialog import LargeFolderWarningDialog
from meshcorral.ui.layout_constants import (
    MOVE_PREVIEW_DIALOG_MIN_HEIGHT,
    MOVE_PREVIEW_DIALOG_MIN_WIDTH,
    SETTINGS_DIALOG_MIN_HEIGHT,
    SETTINGS_DIALOG_MIN_WIDTH,
)
from meshcorral.ui.responsive_dialog import primary_actions_outside_scroll
from meshcorral.ui.dialogs import AboutDialog, ScanOptionsDialog
from meshcorral.ui.responsive_dialog import primary_actions_outside_scroll
from meshcorral.ui.settings_dialog import SettingsDialog
from meshcorral.ui.tags.tag_dialog import TagDialog


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication(sys.argv)
    return inst  # type: ignore[return-value]


class TestCenterDialogOverParent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_center_dialog_within_parent_screen(self) -> None:
        parent = QMainWindow()
        parent.setGeometry(200, 150, 900, 700)
        parent.show()
        dialog = QDialog(parent)
        dialog.resize(400, 300)
        center_dialog_over_parent(dialog, parent)
        parent_frame = parent.frameGeometry()
        dialog_frame = dialog.frameGeometry()
        self.assertTrue(parent_frame.intersects(dialog_frame))
        screen = parent.screen() or QApplication.primaryScreen()
        self.assertIsNotNone(screen)
        if screen is not None:
            available = screen.availableGeometry()
            self.assertTrue(available.contains(dialog_frame.topLeft()))
            self.assertTrue(
                dialog_frame.right() <= available.right() + 1
                and dialog_frame.bottom() <= available.bottom() + 1
            )

    def test_clamp_moves_dialog_onscreen_when_parent_near_edge(self) -> None:
        """A parent pushed against the right edge still yields a fully on-screen dialog.

        The clamp target is the screen the *parent* occupies, which on a multi-monitor
        desktop is not necessarily the primary screen.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            self.skipTest("no primary screen")
        primary = screen.availableGeometry()
        parent = QMainWindow()
        parent.setGeometry(primary.right() - 120, primary.top() + 40, 500, 400)
        parent.show()
        dialog = QDialog(parent)
        dialog.resize(480, 360)
        center_dialog_over_parent(dialog, parent)

        available = available_geometry_for_widget(dialog, parent)
        self.assertIsNotNone(available)
        if available is None:
            return
        moved = dialog.frameGeometry()
        self.assertGreaterEqual(moved.left(), available.left())
        self.assertGreaterEqual(moved.top(), available.top())
        self.assertLessEqual(moved.right(), available.right() + 1)
        self.assertLessEqual(moved.bottom(), available.bottom() + 1)


class TestClampDialogSizeToScreen(unittest.TestCase):
    def test_laptop_height_never_exceeds_available_minus_margin(self) -> None:
        available = QRect(0, 0, 1366, 728)
        _width, height, _max_w, max_h, _min_w, _min_h = clamp_dialog_size_to_screen(
            desired_width=SETTINGS_DIALOG_MIN_WIDTH,
            desired_height=1200,
            min_width=SETTINGS_DIALOG_MIN_WIDTH,
            min_height=SETTINGS_DIALOG_MIN_HEIGHT,
            available=available,
        )
        self.assertLessEqual(height, available.height())
        self.assertLessEqual(height, available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN)
        self.assertEqual(max_h, available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN)


class TestClampFrameRectToAvailable(unittest.TestCase):
    """Pure-geometry clamp, exercised on synthetic multi-monitor coordinate spaces.

    Real monitor layouts vary per developer machine, so the four-edge and
    secondary-monitor cases are driven from explicit rectangles instead of whatever
    screens happen to be attached.
    """

    #: Primary, a monitor to the right (positive offset), and one to the left (negative x).
    WORK_AREAS = {
        "primary": QRect(0, 0, 1920, 1040),
        "right-secondary": QRect(1920, -180, 2560, 1400),
        "left-secondary": QRect(-1600, 120, 1600, 860),
    }

    def _assert_inside(self, rect: QRect, available: QRect) -> None:
        self.assertGreaterEqual(rect.left(), available.left())
        self.assertGreaterEqual(rect.top(), available.top())
        self.assertLessEqual(rect.right(), available.right())
        self.assertLessEqual(rect.bottom(), available.bottom())

    def test_dialog_pulled_back_from_every_edge(self) -> None:
        dialog_w, dialog_h = 720, 560
        for name, available in self.WORK_AREAS.items():
            overhangs = {
                "left": QRect(available.left() - 400, available.center().y(), dialog_w, dialog_h),
                "right": QRect(available.right() - 60, available.center().y(), dialog_w, dialog_h),
                "top": QRect(available.center().x(), available.top() - 300, dialog_w, dialog_h),
                "bottom": QRect(
                    available.center().x(), available.bottom() - 40, dialog_w, dialog_h
                ),
            }
            for edge, target in overhangs.items():
                with self.subTest(screen=name, edge=edge):
                    clamped = clamp_frame_rect_to_available(target, available)
                    self._assert_inside(clamped, available)
                    self.assertEqual(clamped.size(), target.size())

    def test_oversized_dialog_shrinks_to_work_area(self) -> None:
        for name, available in self.WORK_AREAS.items():
            with self.subTest(screen=name):
                target = QRect(
                    available.left() - 500,
                    available.top() - 500,
                    available.width() + 900,
                    available.height() + 900,
                )
                clamped = clamp_frame_rect_to_available(target, available)
                self._assert_inside(clamped, available)
                self.assertEqual(clamped.width(), available.width())
                self.assertEqual(clamped.height(), available.height())

    def test_centering_on_secondary_monitor_keeps_negative_coordinates(self) -> None:
        """A left-hand monitor uses negative x; the clamp must not snap back to 0."""
        available = self.WORK_AREAS["left-secondary"]
        target = QRect(available.center().x() - 300, available.center().y() - 200, 600, 400)
        clamped = clamp_frame_rect_to_available(target, available)
        self._assert_inside(clamped, available)
        self.assertLess(clamped.left(), 0)

    def test_frame_extra_is_deducted_from_size_limits(self) -> None:
        """Title bar + borders come out of the budget so the *frame* fits."""
        available = self.WORK_AREAS["right-secondary"]
        _w, height, _max_w, max_h, _min_w, _min_h = clamp_dialog_size_to_screen(
            desired_width=4000,
            desired_height=4000,
            min_width=SETTINGS_DIALOG_MIN_WIDTH,
            min_height=SETTINGS_DIALOG_MIN_HEIGHT,
            available=available,
            frame_extra_width=16,
            frame_extra_height=39,
        )
        self.assertEqual(max_h, available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN - 39)
        self.assertLessEqual(
            height + 39,
            available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN,
        )

    def test_tiny_work_area_still_returns_positive_size(self) -> None:
        """A work area smaller than the margins must not produce a zero/negative size."""
        width, height, max_w, max_h, min_w, min_h = clamp_dialog_size_to_screen(
            desired_width=SETTINGS_DIALOG_MIN_WIDTH,
            desired_height=SETTINGS_DIALOG_MIN_HEIGHT,
            min_width=SETTINGS_DIALOG_MIN_WIDTH,
            min_height=SETTINGS_DIALOG_MIN_HEIGHT,
            available=QRect(0, 0, 20, 20),
            frame_extra_width=16,
            frame_extra_height=39,
        )
        for value in (width, height, max_w, max_h, min_w, min_h):
            self.assertGreater(value, 0)


class TestScreenResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_unmapped_dialog_inherits_parent_screen(self) -> None:
        """Before mapping, a dialog reports the primary screen; the parent must win."""
        parent = QMainWindow()
        parent.setGeometry(120, 120, 800, 600)
        parent.show()
        dialog = QDialog(parent)
        self.assertIs(screen_for_dialog(dialog, parent), parent.screen())

    def test_parentless_dialog_falls_back_to_a_screen(self) -> None:
        dialog = QDialog()
        self.assertIsNotNone(screen_for_dialog(dialog, None))

    def test_frame_extra_is_never_negative(self) -> None:
        dialog = QDialog()
        dialog.resize(320, 240)
        extra_w, extra_h = dialog_frame_extra(dialog)
        self.assertGreaterEqual(extra_w, 0)
        self.assertGreaterEqual(extra_h, 0)


class TestResponsiveModalDialogBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_subclass_enables_resize_grip(self) -> None:
        dlg = ScanOptionsDialog(parent=None, default_recursive=True)
        self.assertTrue(dlg.isSizeGripEnabled())

    def test_scan_options_primary_buttons_reachable(self) -> None:
        dlg = ScanOptionsDialog(parent=None, default_recursive=False)
        dlg.show()
        self.assertIsNotNone(dlg._button_box)
        if dlg._button_box is None:
            self.fail("missing button box")
        for btn in dlg._button_box.buttons():
            self.assertTrue(btn.isVisible())
            self.assertTrue(btn.isEnabled())

    def test_tag_dialog_save_outside_scroll(self) -> None:
        dlg = TagDialog(parent=None)
        self.assertTrue(primary_actions_outside_scroll(dlg._content_scroll, dlg._button_box))

    def test_about_dialog_clamped_on_show(self) -> None:
        dlg = AboutDialog(parent=None)
        dlg.show()
        available = available_geometry_for_widget(dlg)
        self.assertIsNotNone(available)
        if available is not None:
            self.assertLessEqual(dlg.height(), available.height())


class TestSettingsDialogResponsiveLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_dialog(self, parent: QMainWindow | None = None) -> SettingsDialog:
        ini = QSettings("WoodringToolsTestDialogPlacement", "MeshStagerSettings")
        ini.clear()
        return SettingsDialog(SettingsService(ini), parent)

    def test_save_cancel_outside_scroll_area(self) -> None:
        dlg = self._make_dialog()
        self.assertTrue(
            primary_actions_outside_scroll(dlg._settings_scroll, dlg._button_box)
        )
        self.assertEqual(dlg._button_box.parent().objectName(), "SettingsButtonRow")

    def test_dialog_height_clamped_to_screen_on_show(self) -> None:
        parent = QMainWindow()
        parent.setGeometry(80, 60, 1100, 700)
        parent.show()
        dlg = self._make_dialog(parent)
        dlg.show()
        available = available_geometry_for_widget(dlg)
        self.assertIsNotNone(available)
        if available is not None:
            self.assertLessEqual(dlg.height(), available.height())
            self.assertLessEqual(
                dlg.height(),
                available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN,
            )
            frame = dlg.frameGeometry()
            self.assertGreaterEqual(frame.top(), available.top())
            self.assertLessEqual(frame.bottom(), available.bottom() + 1)

    def test_save_cancel_reachable_after_show(self) -> None:
        dlg = self._make_dialog()
        dlg.show()
        self.assertIsNotNone(dlg._button_box)
        if dlg._button_box is None:
            self.fail("missing button box")
        save_btn = dlg._button_box.button(dlg._button_box.StandardButton.Save)
        cancel_btn = dlg._button_box.button(dlg._button_box.StandardButton.Cancel)
        self.assertIsNotNone(save_btn)
        self.assertIsNotNone(cancel_btn)
        self.assertTrue(save_btn.isVisible())
        self.assertTrue(cancel_btn.isVisible())
        self.assertTrue(save_btn.isEnabled())
        self.assertTrue(cancel_btn.isEnabled())

    def test_ctrl_s_triggers_save(self) -> None:
        dlg = self._make_dialog()
        saved: list[bool] = []

        def _track_save() -> None:
            saved.append(True)

        dlg._save_and_accept = _track_save  # type: ignore[method-assign]
        for action in dlg.actions():
            if action.shortcut() == QKeySequence.StandardKey.Save:
                action.trigger()
                break
        else:
            self.fail("Save shortcut action not found")
        self.assertEqual(saved, [True])

    def test_center_clamp_keeps_settings_dialog_on_screen(self) -> None:
        """Bottom-right parent: the Settings frame stays inside its own screen's work area."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.skipTest("no primary screen")
        primary = screen.availableGeometry()
        parent = QMainWindow()
        parent.setGeometry(primary.right() - 100, primary.bottom() - 120, 640, 480)
        parent.show()
        dlg = self._make_dialog(parent)
        dlg.show()

        available = available_geometry_for_widget(dlg, parent)
        self.assertIsNotNone(available)
        if available is None:
            return
        frame = dlg.frameGeometry()
        self.assertGreaterEqual(frame.left(), available.left())
        self.assertGreaterEqual(frame.top(), available.top())
        self.assertLessEqual(frame.right(), available.right() + 1)
        self.assertLessEqual(frame.bottom(), available.bottom() + 1)

    def test_settings_dialog_clamped_for_parent_at_each_screen_edge(self) -> None:
        """Save/Cancel stay reachable with the parent hugging every screen edge."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.skipTest("no primary screen")
        primary = screen.availableGeometry()
        corners = {
            "top-left": (primary.left(), primary.top()),
            "top-right": (primary.right() - 200, primary.top()),
            "bottom-left": (primary.left(), primary.bottom() - 200),
            "bottom-right": (primary.right() - 200, primary.bottom() - 200),
        }
        for label, (x, y) in corners.items():
            with self.subTest(edge=label):
                parent = QMainWindow()
                parent.setGeometry(x, y, 600, 450)
                parent.show()
                dlg = self._make_dialog(parent)
                dlg.show()

                available = available_geometry_for_widget(dlg, parent)
                self.assertIsNotNone(available)
                if available is None:
                    continue
                frame = dlg.frameGeometry()
                self.assertGreaterEqual(frame.left(), available.left())
                self.assertGreaterEqual(frame.top(), available.top())
                self.assertLessEqual(frame.right(), available.right() + 1)
                self.assertLessEqual(frame.bottom(), available.bottom() + 1)
                self.assertTrue(
                    dlg._button_box.button(dlg._button_box.StandardButton.Save).isVisible()
                )
                self.assertTrue(
                    dlg._button_box.button(dlg._button_box.StandardButton.Cancel).isVisible()
                )
                dlg.close()
                parent.close()

    def test_settings_dialog_sized_for_parent_screen_not_primary(self) -> None:
        """Sizing must use the parent's screen work area, not the primary screen's."""
        screens = QApplication.screens()
        secondary = next(
            (s for s in screens if s is not QApplication.primaryScreen()),
            None,
        )
        if secondary is None:
            self.skipTest("single-monitor host; covered synthetically by clamp tests")
        available = secondary.availableGeometry()
        parent = QMainWindow()
        parent.setGeometry(available.left() + 20, available.top() + 20, 700, 500)
        parent.show()
        dlg = self._make_dialog(parent)
        dlg.show()

        self.assertIs(screen_for_dialog(dlg, parent), secondary)
        frame_extra_w, frame_extra_h = dialog_frame_extra(dlg)
        self.assertLessEqual(
            dlg.height() + frame_extra_h,
            available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN,
        )
        self.assertLessEqual(
            dlg.width() + frame_extra_w,
            available.width() - SETTINGS_DIALOG_HORIZONTAL_MARGIN,
        )


class TestLargeFolderWarningResponsiveLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _sample_assessment(self) -> object:
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
            return_value=True,
        ), mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            from meshcorral.services.large_folder_scan_assessment import (
                FolderScopeEstimate,
                build_large_folder_assessment,
            )

            mock_preflight.return_value = FolderScopeEstimate(
                matching_file_count=3000,
                exceeds_file_threshold=True,
                archive_zip_count=0,
                max_directory_depth=3,
                preflight_truncated=True,
            )
            from meshcorral.services.large_folder_scan_assessment import (
                LargeFolderWarningPersistence,
            )

            return build_large_folder_assessment(
                r"\\srv\lib",
                recursive=True,
                allowed_extensions={".stl"},
                settings_service=SettingsService(),
                persistence=LargeFolderWarningPersistence(QSettings()),
                prior_cached_count=0,
            )

    def test_primary_actions_outside_scroll_area(self) -> None:
        dlg = LargeFolderWarningDialog(self._sample_assessment(), parent=None)
        self.assertTrue(
            primary_actions_outside_scroll(dlg._content_scroll, dlg._continue_btn)
        )

    def test_dialog_height_clamped_on_laptop_geometry(self) -> None:
        dlg = LargeFolderWarningDialog(self._sample_assessment(), parent=None)
        dlg.show()
        available = available_geometry_for_widget(dlg)
        self.assertIsNotNone(available)
        if available is not None:
            self.assertLessEqual(dlg.height(), available.height())
            self.assertLessEqual(
                dlg.height(),
                available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN,
            )

    def test_continue_cancel_reachable_after_show(self) -> None:
        dlg = LargeFolderWarningDialog(self._sample_assessment(), parent=None)
        dlg.show()
        self.assertTrue(dlg._continue_btn.isVisible())
        self.assertTrue(dlg._cancel_btn.isVisible())
        self.assertTrue(dlg._continue_btn.isEnabled())
        self.assertTrue(dlg._cancel_btn.isEnabled())


class TestMovePreviewResponsiveLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_dialog_height_clamped_to_screen(self) -> None:
        plan = [
            MovePlan(
                source_path=Path("C:/a.stl"),
                destination_path=Path("D:/a.stl"),
                status="OK",
                message="",
            )
        ]
        dlg = MovePreviewDialog(parent=None, plan=plan, is_copy=False)
        dlg.show()
        available = available_geometry_for_widget(dlg)
        self.assertIsNotNone(available)
        if available is not None:
            self.assertLessEqual(dlg.height(), available.height())
            self.assertLessEqual(
                dlg.height(),
                available.height() - SETTINGS_DIALOG_VERTICAL_MARGIN,
            )
            self.assertGreaterEqual(dlg.minimumWidth(), MOVE_PREVIEW_DIALOG_MIN_WIDTH)
            self.assertGreaterEqual(dlg.minimumHeight(), MOVE_PREVIEW_DIALOG_MIN_HEIGHT)

    def test_primary_buttons_reachable(self) -> None:
        dlg = MovePreviewDialog(parent=None, plan=[], is_copy=True)
        dlg.show()
        self.assertIsNotNone(dlg._button_box)
        if dlg._button_box is None:
            self.fail("missing button box")
        visible_buttons = [
            dlg._button_box.buttons()[i]
            for i in range(len(dlg._button_box.buttons()))
        ]
        self.assertGreaterEqual(len(visible_buttons), 2)
        for btn in visible_buttons:
            self.assertTrue(btn.isVisible())
            self.assertTrue(btn.isEnabled())


if __name__ == "__main__":
    unittest.main()
