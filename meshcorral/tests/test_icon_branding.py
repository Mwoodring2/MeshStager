"""Focused application icon, Windows identity and frozen resource regression checks."""
from __future__ import annotations

import ast
import ctypes
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from meshcorral.app import icon_branding as branding


class TestIconBranding(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_source_icon_resolves_and_decodes(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(branding._resource_root(), Path(__file__).resolve().parents[2])
        self.assertTrue(branding.icon_ico_path().is_file())
        self.assertFalse(branding.application_icon().pixmap(32, 32).isNull())

    def test_frozen_bundle_loads_real_icon_without_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            icons = root / "assets" / "icons"
            icons.mkdir(parents=True)
            shutil.copyfile(branding.ICON_ICO, icons / branding.ICON_ICO.name)
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", td, create=True):
                spec = importlib.util.spec_from_file_location("_bundled_icon_branding", branding.__file__)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertEqual(module.icon_ico_path(), icons / branding.ICON_ICO.name)
                self.assertFalse(module.application_icon().pixmap(32, 32).isNull())

    def test_missing_and_corrupt_icons_log_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "broken.ico"
            bad.write_bytes(b"not an icon")
            with patch.object(branding, "_APP_ICON_CANDIDATES", (bad, bad.with_name("missing.ico"))):
                with self.assertLogs(branding.logger, level="WARNING"):
                    self.assertTrue(branding.application_icon().isNull())

    def test_corrupt_ico_falls_back_to_existing_png(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "broken.ico"
            bad.write_bytes(b"not an icon")
            with patch.object(branding, "_APP_ICON_CANDIDATES", (bad, branding.ICON_PNG)):
                with self.assertLogs(branding.logger, level="WARNING"):
                    self.assertFalse(branding.application_icon().pixmap(32, 32).isNull())

    def test_inaccessible_asset_logs_and_returns_empty_icon(self) -> None:
        with patch.object(Path, "is_file", side_effect=OSError("denied")):
            with self.assertLogs(branding.logger, level="WARNING"):
                self.assertTrue(branding.application_icon().isNull())

    def test_windows_identity_success_uses_unicode_signature(self) -> None:
        setter = Mock(return_value=0)
        library = SimpleNamespace(shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter))
        with patch.object(sys, "platform", "win32"), patch.object(ctypes, "windll", library, create=True):
            self.assertTrue(branding.set_windows_app_user_model_id())
        setter.assert_called_once_with(branding.WINDOWS_APP_USER_MODEL_ID)
        self.assertEqual(setter.argtypes, [ctypes.c_wchar_p])
        self.assertEqual(setter.restype, ctypes.c_long)

    def test_windows_identity_failures_are_logged_and_safe(self) -> None:
        for result in (-2147467259, OSError("unavailable")):
            setter = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
            library = SimpleNamespace(shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter))
            with self.subTest(result=result), patch.object(sys, "platform", "win32"), patch.object(ctypes, "windll", library, create=True):
                with self.assertLogs(branding.logger, level="WARNING"):
                    self.assertFalse(branding.set_windows_app_user_model_id())

    def test_non_windows_does_not_call_shell_api(self) -> None:
        with patch.object(sys, "platform", "linux"), patch.object(ctypes, "windll", Mock(), create=True) as library:
            self.assertFalse(branding.set_windows_app_user_model_id())
            library.shell32.SetCurrentProcessExplicitAppUserModelID.assert_not_called()

    def test_spec_embeds_executable_icon_and_collects_runtime_assets(self) -> None:
        root = Path(__file__).resolve().parents[2]
        tree = ast.parse((root / "MeshStager.spec").read_text(encoding="utf-8"))
        calls = {node.func.id: node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        datas = next(ast.literal_eval(k.value) for k in calls["Analysis"].keywords if k.arg == "datas")
        icons = next(ast.literal_eval(k.value) for k in calls["EXE"].keywords if k.arg == "icon")
        self.assertIn(("assets/icons", "assets/icons"), datas)
        self.assertIn("assets/icons/MeshStager_icon.ico", icons)

    def test_startup_sets_identity_before_application_and_same_window_icon(self) -> None:
        from meshcorral.app import main as startup
        from meshcorral.services.settings_service import SettingsService
        from meshcorral.ui.main_window import MainWindow
        events = []
        original_icon = self.app.windowIcon()
        self.addCleanup(self.app.setWindowIcon, original_icon)
        windows = []
        with tempfile.TemporaryDirectory() as td:
            class IsolatedSettings(SettingsService):
                def __init__(self):
                    super().__init__(QSettings(str(Path(td) / "settings.ini"), QSettings.Format.IniFormat))

            def create_app(argv):
                events.append("app")
                return self.app

            def create_window():
                events.append("window")
                self.assertFalse(self.app.windowIcon().pixmap(32, 32).isNull())
                window = MainWindow()
                windows.append(window)
                self.assertEqual(window.windowIcon().cacheKey(), self.app.windowIcon().cacheKey())
                return window

            def check_present(window):
                self.assertFalse(window.windowIcon().pixmap(32, 32).isNull())
                self.assertEqual(window.windowIcon().cacheKey(), self.app.windowIcon().cacheKey())

            with patch.object(startup, "configure_logging"), patch.object(startup, "set_windows_app_user_model_id", side_effect=lambda: events.append("identity")), patch.object(startup, "QApplication", side_effect=create_app), patch.object(startup, "MainWindow", side_effect=create_window), patch.object(startup, "SettingsService", IsolatedSettings), patch("meshcorral.ui.main_window.SettingsService", IsolatedSettings), patch.object(startup, "apply_theme_palette"), patch.object(startup, "present_main_window", side_effect=check_present), patch.object(self.app, "exec", return_value=0):
                try:
                    self.assertEqual(startup.main(), 0)
                finally:
                    for window in windows:
                        window.close()
                        window.deleteLater()
            self.assertEqual(events, ["identity", "app", "window"])
