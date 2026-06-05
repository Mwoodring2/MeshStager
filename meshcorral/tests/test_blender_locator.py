"""Unit tests for :mod:`meshcorral.app.bridge.blender_locator`."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge import blender_locator
from meshcorral.app.bridge.blender_locator import (
    describe_blender_readiness,
    find_blender_executable,
    get_blender_version,
    validate_blender_path,
)
from meshcorral.services.settings_service import SettingsService


class TestBlenderLocator(unittest.TestCase):
    """Test Blender path discovery and --version without requiring Blender installed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._fake_blender = Path(self._tmp.name) / "blender.exe"
        self._fake_blender.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_get_blender_version_success(self) -> None:
        with patch.object(
            blender_locator,
            "_run_version_subprocess",
            return_value=(0, "Blender 4.2.0", ""),
        ) as m:
            v = get_blender_version(self._fake_blender)
        m.assert_called_once()
        self.assertEqual(v, "Blender 4.2.0")
        self.assertFalse(v.startswith("Error:"))

    def test_get_blender_version_missing_file(self) -> None:
        missing = Path(self._tmp.name) / "nope.exe"
        v = get_blender_version(missing)
        self.assertIn("Error:", v)
        self.assertIn("does not exist", v)

    def test_get_blender_version_nonzero_exit(self) -> None:
        with patch.object(
            blender_locator,
            "_run_version_subprocess",
            return_value=(1, "", "not blender"),
        ):
            v = get_blender_version(self._fake_blender)
        self.assertIn("Error:", v)
        self.assertIn("exit 1", v)

    def test_get_blender_version_timeout(self) -> None:
        with patch.object(
            blender_locator,
            "_run_version_subprocess",
            return_value=(-1, "", "Timed out after 15 seconds."),
        ):
            v = get_blender_version(self._fake_blender)
        self.assertIn("Error:", v)

    def test_validate_blender_path_true(self) -> None:
        with patch.object(
            blender_locator,
            "_run_version_subprocess",
            return_value=(0, "Blender 4.0.0", ""),
        ):
            self.assertTrue(validate_blender_path(self._fake_blender))

    def test_validate_blender_path_false(self) -> None:
        with patch.object(
            blender_locator,
            "_run_version_subprocess",
            return_value=(1, "", "fail"),
        ):
            self.assertFalse(validate_blender_path(self._fake_blender))

    def test_find_blender_executable_uses_settings(self) -> None:
        ini_path = str(Path(self._tmp.name) / "test.ini")
        qs = QSettings(ini_path, QSettings.Format.IniFormat)
        qs.clear()
        svc = SettingsService(qs)
        svc.set_blender_executable(str(self._fake_blender))
        with patch.object(
            blender_locator,
            "_scan_for_blender_exe",
            return_value=[],
        ):
            p = find_blender_executable(svc)
        self.assertIsNotNone(p)
        self.assertEqual(p, self._fake_blender.resolve())

    def test_find_blender_executable_none_when_unconfigured(self) -> None:
        with patch.object(blender_locator, "_scan_for_blender_exe", return_value=[]):
            p = find_blender_executable()
        self.assertIsNone(p)

    def test_describe_blender_readiness_ready(self) -> None:
        """Any resolved path yields Ready without invoking Blender."""
        ini_path = str(Path(self._tmp.name) / "ready.ini")
        qs = QSettings(ini_path, QSettings.Format.IniFormat)
        qs.clear()
        svc = SettingsService(qs)
        label = describe_blender_readiness(svc, self._fake_blender.resolve())
        self.assertEqual(label, "Ready")

    def test_describe_blender_readiness_not_configured(self) -> None:
        """Empty stored path and no locator hit means Not configured."""
        ini_path = str(Path(self._tmp.name) / "nc.ini")
        qs = QSettings(ini_path, QSettings.Format.IniFormat)
        qs.clear()
        svc = SettingsService(qs)
        label = describe_blender_readiness(svc, None)
        self.assertEqual(label, "Not configured")

    def test_describe_blender_readiness_not_found(self) -> None:
        """Stored path but locator still None means Not found (misconfiguration)."""
        ini_path = str(Path(self._tmp.name) / "nf.ini")
        qs = QSettings(ini_path, QSettings.Format.IniFormat)
        qs.clear()
        svc = SettingsService(qs)
        svc.set_blender_executable(r"C:\no\such\blender_for_roundup_test.exe")
        label = describe_blender_readiness(svc, None)
        self.assertEqual(label, "Not found")
