"""Headless branding smoke checks for MeshStager rebrand verification."""

from __future__ import annotations

import sys
import unittest

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel

from meshcorral.app.config import APP_NAME, APP_VERSION, LEGACY_APP_NAME
from meshcorral.app.icon_branding import (
    BRANDING_PRO_JPG,
    ICON_ICO,
    ICON_PNG,
    ICON_TOOLBAR_PNG,
    WINDOWS_APP_USER_MODEL_ID,
    application_icon,
    header_branding_icon_path,
    icon_ico_path,
    icon_png_path,
    marketing_branding_image_path,
    set_windows_app_user_model_id,
    toolbar_icon_png_path,
)
from meshcorral.ui.branding import HEADER_ICON_DISPLAY_PX, HEADER_ICON_TITLE_SPACING_PX, BrandHeader
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.dialogs import AboutDialog
from meshcorral.ui.empty_states import FRESH_LAUNCH, empty_state_spec
from meshcorral.ui.settings_dialog import SettingsDialog
from meshcorral.ui.thumbnails.thumbnail_ux_copy import (
    REASON_DEFERRED_PERF,
    REASON_FAILED_GENERIC,
)


class TestBrandingSmoke(unittest.TestCase):
    """Verify customer-visible strings without manual GUI inspection."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_app_identity_constants(self) -> None:
        self.assertEqual(APP_NAME, "MeshStager")
        self.assertEqual(LEGACY_APP_NAME, "Roundup")
        self.assertEqual(SettingsService.APP_NAME, "MeshStager")

    def test_welcome_empty_state_title(self) -> None:
        state = empty_state_spec(FRESH_LAUNCH)
        self.assertIn("MeshStager", state.title)
        self.assertNotIn("Welcome to Roundup", state.title)

    def test_settings_dialog_header(self) -> None:
        ini = QSettings("WoodringToolsTestBranding", "MeshStagerSmoke")
        ini.clear()
        dlg = SettingsDialog(SettingsService(ini))
        header_texts = [w.text() for w in dlg.findChildren(QLabel)]
        self.assertIn("MeshStager Settings", header_texts)

    def test_thumbnail_ux_copy_uses_meshstager(self) -> None:
        self.assertIn("MeshStager", REASON_DEFERRED_PERF)
        self.assertIn("MeshStager", REASON_FAILED_GENERIC)
        self.assertNotIn("Roundup delayed", REASON_DEFERRED_PERF)

    def test_about_dialog_title(self) -> None:
        dlg = AboutDialog(parent=None)
        self.assertEqual(dlg.windowTitle(), f"About {APP_NAME}")
        self.assertEqual(APP_NAME, "MeshStager")
        self.assertTrue(APP_VERSION)

    def test_official_icon_assets_present(self) -> None:
        self.assertTrue(ICON_PNG.is_file())
        self.assertTrue(ICON_ICO.is_file())
        self.assertEqual(icon_ico_path(), ICON_ICO)
        self.assertFalse(application_icon().isNull())

    def test_toolbar_icon_asset_present(self) -> None:
        self.assertTrue(ICON_TOOLBAR_PNG.is_file())
        self.assertEqual(toolbar_icon_png_path(), ICON_TOOLBAR_PNG)

    def test_branding_paths_resolve(self) -> None:
        self.assertEqual(icon_png_path(), ICON_PNG)
        self.assertEqual(header_branding_icon_path(), ICON_TOOLBAR_PNG)
        marketing = marketing_branding_image_path()
        if BRANDING_PRO_JPG.is_file():
            self.assertEqual(marketing, BRANDING_PRO_JPG)
        else:
            self.assertIsNone(marketing)

    def test_header_uses_toolbar_icon_not_app_png(self) -> None:
        self.assertNotEqual(header_branding_icon_path(), icon_png_path())
        header = BrandHeader(
            app_name=APP_NAME,
            subtitle="Find and organize your files safely",
            icon_path=header_branding_icon_path(),
        )
        self.assertEqual(header.icon_label.width(), HEADER_ICON_DISPLAY_PX)
        self.assertEqual(header.icon_label.height(), HEADER_ICON_DISPLAY_PX)
        self.assertGreaterEqual(HEADER_ICON_DISPLAY_PX, 32)
        self.assertLessEqual(HEADER_ICON_DISPLAY_PX, 40)
        self.assertEqual(HEADER_ICON_TITLE_SPACING_PX, 10)
        self.assertFalse(header.icon_label.pixmap().isNull())

    def test_windows_app_user_model_id_constant(self) -> None:
        self.assertEqual(WINDOWS_APP_USER_MODEL_ID, "MeshStager.MeshStager.RC3")

    def test_set_windows_app_user_model_id_no_crash(self) -> None:
        if sys.platform == "win32":
            set_windows_app_user_model_id()
        else:
            self.assertFalse(set_windows_app_user_model_id())


if __name__ == "__main__":
    unittest.main()
