"""Tests for :class:`meshcorral.services.settings_service.SettingsService`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from meshcorral.services.settings_service import SettingsService


class TestSettingsService(unittest.TestCase):
    """Use a temporary INI file so tests do not touch real user settings."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini_path = str(Path(self._tmp.name) / "test_meshcorral.ini")
        self._qs = QSettings(ini_path, QSettings.Format.IniFormat)
        self._qs.clear()
        self.svc = SettingsService(self._qs)

    def tearDown(self) -> None:
        self._qs.clear()
        self._tmp.cleanup()

    def test_app_name_is_meshstager(self) -> None:
        self.assertEqual(SettingsService.APP_NAME, "MeshStager")

    def test_theme_mode_invalid_falls_back_to_dark(self) -> None:
        self._qs.setValue(SettingsService.KEY_THEME, "neon")
        self.assertEqual(self.svc.theme_mode(), "dark")

    def test_set_theme_mode_clamps_unknown(self) -> None:
        self.svc.set_theme_mode("invalid")
        self.assertEqual(self._qs.value(SettingsService.KEY_THEME), "dark")

    def test_read_bool_from_string(self) -> None:
        self._qs.setValue(SettingsService.KEY_CONFIRM_BEFORE_MOVE, "false")
        svc = SettingsService(self._qs)
        self.assertFalse(svc.confirm_before_move())

    def test_default_destination_strip_on_write(self) -> None:
        self.svc.set_default_destination("  D:\\tmp  ")
        self.assertEqual(self.svc.default_destination(), "D:\\tmp")

    def test_search_mode_default_is_3d(self) -> None:
        self.assertEqual(self.svc.search_mode(), "3d")

    def test_search_mode_invalid_falls_back_to_3d(self) -> None:
        self._qs.setValue(SettingsService.KEY_SEARCH_MODE, "other")
        svc = SettingsService(self._qs)
        self.assertEqual(svc.search_mode(), "3d")

    def test_set_search_mode_clamps_invalid(self) -> None:
        self.svc.set_search_mode("other")
        self.assertEqual(self._qs.value(SettingsService.KEY_SEARCH_MODE), "3d")
        self.assertEqual(self.svc.search_mode(), "3d")

    def test_blender_executable_strip_on_write(self) -> None:
        self.svc.set_blender_executable("  C:/Program Files/Blender Foundation/Blender 4.4/blender.exe  ")
        self.assertEqual(
            self.svc.blender_executable(),
            "C:/Program Files/Blender Foundation/Blender 4.4/blender.exe",
        )

    def test_search_mode_round_trip(self) -> None:
        self.svc.set_search_mode("images")
        self.assertEqual(self.svc.search_mode(), "images")
        svc2 = SettingsService(self._qs)
        self.assertEqual(svc2.search_mode(), "images")

    def test_auto_thumbnail_defaults(self) -> None:
        self.assertFalse(self.svc.auto_thumbnail_after_scan())
        self.assertEqual(
            self.svc.auto_thumbnail_max_per_scan(),
            SettingsService.CAP_AUTO_THUMB_25,
        )

    def test_auto_thumbnail_max_invalid_falls_back_to_25(self) -> None:
        self._qs.setValue(
            SettingsService.KEY_AUTO_THUMBNAIL_MAX_PER_SCAN,
            9999,
        )
        svc = SettingsService(self._qs)
        self.assertEqual(svc.auto_thumbnail_max_per_scan(), SettingsService.CAP_AUTO_THUMB_25)

    def test_auto_thumbnail_round_trip(self) -> None:
        self.svc.set_auto_thumbnail_after_scan(True)
        self.svc.set_auto_thumbnail_max_per_scan(SettingsService.CAP_AUTO_THUMB_UNLIMITED)
        svc2 = SettingsService(self._qs)
        self.assertTrue(svc2.auto_thumbnail_after_scan())
        self.assertEqual(
            svc2.auto_thumbnail_max_per_scan(),
            SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )

    def test_browse_view_mode_default_table(self) -> None:
        self.assertEqual(self.svc.browse_view_mode(), SettingsService.VIEW_MODE_TABLE)

    def test_browse_view_mode_invalid_falls_back(self) -> None:
        self._qs.setValue(SettingsService.KEY_BROWSE_VIEW_MODE, "invalid")
        svc = SettingsService(self._qs)
        self.assertEqual(svc.browse_view_mode(), SettingsService.VIEW_MODE_TABLE)

    def test_browse_view_mode_round_trip(self) -> None:
        self.svc.set_browse_view_mode(SettingsService.VIEW_MODE_GALLERY)
        self.assertEqual(
            SettingsService(self._qs).browse_view_mode(),
            SettingsService.VIEW_MODE_GALLERY,
        )

    def test_thumbnail_display_pixels_default(self) -> None:
        self.assertEqual(
            self.svc.thumbnail_display_pixels(),
            SettingsService.THUMB_PIXELS_48,
        )

    def test_thumbnail_display_pixels_clamps_invalid(self) -> None:
        self._qs.setValue(SettingsService.KEY_THUMBNAIL_DISPLAY_PIXELS, 13)
        svc = SettingsService(self._qs)
        self.assertEqual(svc.thumbnail_display_pixels(), SettingsService.THUMB_PIXELS_48)

    def test_thumbnail_display_pixels_round_trip(self) -> None:
        self.svc.set_thumbnail_display_pixels(256)
        self.assertEqual(
            SettingsService(self._qs).thumbnail_display_pixels(), 256
        )

    def test_bridge_history_keep_days_default_is_30(self) -> None:
        self.assertEqual(
            self.svc.bridge_history_keep_days(),
            SettingsService.BRIDGE_HISTORY_DAYS_DEFAULT,
        )

    def test_bridge_history_keep_days_round_trip(self) -> None:
        self.svc.set_bridge_history_keep_days(SettingsService.BRIDGE_HISTORY_FOREVER_DAYS)
        svc2 = SettingsService(self._qs)
        self.assertEqual(svc2.bridge_history_keep_days(), SettingsService.BRIDGE_HISTORY_FOREVER_DAYS)
        self.svc.set_bridge_history_keep_days(90)
        self.assertEqual(SettingsService(self._qs).bridge_history_keep_days(), 90)
