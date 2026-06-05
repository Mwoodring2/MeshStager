"""Tests for DCC registry + Maya open gating (no Maya install required)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

from meshcorral.app.dcc.dcc_profiles import MAYA_PROFILE, BLENDER_PROFILE
from meshcorral.app.dcc import maya_locator
from meshcorral.app.dcc.maya_locator import find_maya_executable
from meshcorral.services.settings_service import SettingsService


class TestMayaProfile(unittest.TestCase):
    def test_maya_profile_supports_ma_mb(self) -> None:
        self.assertIn(".ma", MAYA_PROFILE.supported_extensions)
        self.assertIn(".mb", MAYA_PROFILE.supported_extensions)
        self.assertTrue(MAYA_PROFILE.capabilities.can_open)
        self.assertFalse(MAYA_PROFILE.capabilities.can_generate_thumbnails)

    def test_blender_support_unchanged(self) -> None:
        self.assertIn(".blend", BLENDER_PROFILE.supported_extensions)
        self.assertTrue(BLENDER_PROFILE.capabilities.can_generate_thumbnails)


class TestMayaLocatorGating(unittest.TestCase):
    def test_maya_open_disabled_when_no_path(self) -> None:
        ini_path = str(Path(tempfile.mkdtemp()) / "maya_none.ini")
        qs = QSettings(ini_path, QSettings.Format.IniFormat)
        qs.clear()
        svc = SettingsService(qs)
        with patch.object(maya_locator.shutil, "which", return_value=None), patch.object(
            maya_locator, "_scan_for_maya_exe", return_value=[]
        ):
            self.assertIsNone(find_maya_executable(svc))

    def test_maya_open_enabled_when_manual_path_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "maya.exe"
            fake.write_text("", encoding="utf-8")
            ini_path = str(Path(td) / "maya_yes.ini")
            qs = QSettings(ini_path, QSettings.Format.IniFormat)
            qs.clear()
            svc = SettingsService(qs)
            svc.set_maya_executable(str(fake))
            out = find_maya_executable(svc)
            self.assertIsNotNone(out)
            self.assertEqual(out, fake.resolve())


if __name__ == "__main__":
    unittest.main()

