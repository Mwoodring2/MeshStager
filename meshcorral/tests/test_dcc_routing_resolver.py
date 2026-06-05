"""Tests for DCC routing resolver helpers (profile-based, not UI-hardcoded)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

from meshcorral.app.dcc.dcc_profiles import (
    BLENDER_PROFILE,
    MAYA_PROFILE,
    configured_executable_for_profile,
    dcc_profile_for_extension,
)
from meshcorral.app.dcc import maya_locator
from meshcorral.services.settings_service import SettingsService


class TestDccResolverHelpers(unittest.TestCase):
    def test_profile_resolution_uses_extension_mapping(self) -> None:
        self.assertIs(dcc_profile_for_extension(".blend"), BLENDER_PROFILE)
        self.assertIs(dcc_profile_for_extension(".ma"), MAYA_PROFILE)
        self.assertIsNone(dcc_profile_for_extension(".fbx"))

    def test_configured_executable_prefers_manual_setting(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "maya.exe"
            fake.write_text("", encoding="utf-8")
            ini_path = str(Path(td) / "settings.ini")
            qs = QSettings(ini_path, QSettings.Format.IniFormat)
            qs.clear()
            svc = SettingsService(qs)
            svc.set_maya_executable(str(fake))

            with patch.object(maya_locator, "find_maya_executable", return_value=None):
                out = configured_executable_for_profile(MAYA_PROFILE, svc)
            self.assertEqual(out, fake.resolve())

    def test_configured_executable_uses_locator_when_manual_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini_path = str(Path(td) / "settings.ini")
            qs = QSettings(ini_path, QSettings.Format.IniFormat)
            qs.clear()
            svc = SettingsService(qs)
            self.assertEqual(svc.maya_executable(), "")

            found = (Path(td) / "auto_maya.exe").resolve()
            found.write_text("", encoding="utf-8")
            with patch.object(maya_locator, "find_maya_executable", return_value=found):
                out = configured_executable_for_profile(MAYA_PROFILE, svc)
            self.assertEqual(out, found)


if __name__ == "__main__":
    unittest.main()

