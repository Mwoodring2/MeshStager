"""Fresh-launch idle session: no auto-scan; warm reopen only on manual open.

Proves that ``paths/last_scan_folder`` and metadata caches survive while
application startup stays empty until the user Browses / opens a source.
"""

from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.app.config import supported_extensions_for_asset_mode
from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata_cache import MetadataCache


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst  # type: ignore[return-value]


class _SettingsSandbox:
    """Per-test QSettings scope."""

    def __init__(self) -> None:
        self._org_name = QCoreApplication.organizationName() or ""
        self._app_name = QCoreApplication.applicationName() or ""
        self._test_id = f"meshcorral-idle-{uuid.uuid4().hex[:8]}"

    def __enter__(self) -> "_SettingsSandbox":
        QCoreApplication.setOrganizationName("MeshCorralIdleTests")
        QCoreApplication.setApplicationName(self._test_id)
        QSettings().clear()
        return self

    def __exit__(self, *exc) -> None:  # type: ignore[no-untyped-def]
        QSettings().clear()
        QCoreApplication.setOrganizationName(self._org_name)
        QCoreApplication.setApplicationName(self._app_name)


class TestIdleStartupSession(unittest.TestCase):
    """Fresh launch must not auto-activate or scan the previous source."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_previous_source_in_settings_does_not_auto_scan(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = MetadataCache(root / "metadata.sqlite")
            try:
                rec = FileRecord(root / "a.stl", "a.stl", ".stl", root.name, 1, 1.0)
                cache.complete_source_snapshot(root, True, {".stl"}, [rec])
                QSettings().setValue("paths/last_scan_folder", td)
                QSettings().setValue("ui/theme_mode", "dark")

                run_scan = Mock()
                with patch(
                    "meshcorral.ui.main_window.MainWindow._ensure_metadata_cache",
                    return_value=cache,
                ), patch(
                    "meshcorral.ui.main_window.MainWindow._run_scan",
                    run_scan,
                ):
                    window = self._make_window()
                    try:
                        for _ in range(20):
                            self.app.processEvents()
                            time.sleep(0.005)

                        self.assertEqual(window._selected_source_path, "")
                        self.assertEqual(window._current_source, "")
                        self.assertEqual(window._model.rowCount(), 0)
                        self.assertEqual(window._gallery_model.rowCount(), 0)
                        self.assertFalse(window._is_scanning)
                        self.assertFalse(window._scan_launch_pending)
                        run_scan.assert_not_called()
                        self.assertEqual(
                            QSettings().value("paths/last_scan_folder", "", type=str),
                            td,
                        )
                        self.assertTrue(cache.has_complete_source(root, True, {".stl"}))
                    finally:
                        window.close()
                        self.app.processEvents()
            finally:
                cache.close()

    def test_layout_theme_and_last_folder_still_available(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            QSettings().setValue("paths/last_scan_folder", td)
            QSettings().setValue("ui/theme_mode", "light")
            window = self._make_window()
            try:
                self.assertEqual(window._last_scan_folder, td)
                self.assertEqual(window._selected_source_path, "")
                self.assertEqual(
                    QSettings().value("ui/theme_mode", "", type=str),
                    "light",
                )
                self.assertGreater(window.width(), 0)
                self.assertGreater(window.height(), 0)
            finally:
                window.close()

    def test_manual_persist_still_warm_reopens(self) -> None:
        """Manual source selection still schedules warm reopen for a complete catalog."""
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = MetadataCache(root / "metadata.sqlite")
            try:
                QSettings().setValue("paths/last_scan_folder", "")
                window = self._make_window()
                try:
                    self.assertEqual(window._selected_source_path, "")
                    self.assertEqual(window._model.rowCount(), 0)

                    rec = FileRecord(root / "cached.stl", "cached.stl", ".stl", root.name, 1, 1.0)
                    cache.complete_source_snapshot(
                        root,
                        window._include_subfolders_checkbox.isChecked(),
                        supported_extensions_for_asset_mode(window._asset_mode),
                        [rec],
                    )
                    run_scan = Mock()
                    window._ensure_metadata_cache = lambda: cache  # type: ignore[method-assign]
                    window._run_scan = run_scan  # type: ignore[method-assign]

                    window._persist_selected_source(td)
                    for _ in range(40):
                        self.app.processEvents()
                        if run_scan.called:
                            break
                        time.sleep(0.01)

                    self.assertEqual(window._selected_source_path, td)
                    run_scan.assert_called_once_with(td)
                    self.assertEqual(
                        QSettings().value("paths/last_scan_folder", "", type=str),
                        td,
                    )
                finally:
                    window.close()
                    self.app.processEvents()
            finally:
                cache.close()

    def test_shutdown_persists_last_folder(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            QSettings().setValue("paths/last_scan_folder", "old-path")
            window = self._make_window()
            try:
                window._selected_source_path = td
                window.close()
                self.app.processEvents()
                self.assertEqual(
                    QSettings().value("paths/last_scan_folder", "", type=str),
                    td,
                )
            finally:
                if not getattr(window, "_shutting_down", False):
                    window.close()


if __name__ == "__main__":
    unittest.main()
