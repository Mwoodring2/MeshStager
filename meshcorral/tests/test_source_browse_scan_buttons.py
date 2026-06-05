"""Tests for separate Browse and Scan Source buttons in the Source panel."""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.app.config import ASSET_MODE_3D, ASSET_MODE_IMAGES
from meshcorral.tests.scan_test_helpers import stub_immediate_scan_launch


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst  # type: ignore[return-value]


class _SettingsSandbox:
    def __init__(self) -> None:
        self._org = QCoreApplication.organizationName() or ""
        self._app = QCoreApplication.applicationName() or ""
        self._test_id = f"meshcorral-tests-{uuid.uuid4().hex[:8]}"

    def __enter__(self) -> "_SettingsSandbox":
        QCoreApplication.setOrganizationName("MeshCorralTests")
        QCoreApplication.setApplicationName(self._test_id)
        QSettings().clear()
        return self

    def __exit__(self, *exc) -> None:  # type: ignore[no-untyped-def]
        QSettings().clear()
        QCoreApplication.setOrganizationName(self._org)
        QCoreApplication.setApplicationName(self._app)


def _combo_index_for(window, mode: str) -> int:  # type: ignore[no-untyped-def]
    for i in range(window._search_mode_combo.count()):
        if window._search_mode_combo.itemData(i) == mode:
            return i
    return -1


class TestBrowseScanButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_browse_sets_selected_source_without_scanning(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                run_scan_calls: list[str] = []
                window._run_scan = lambda p: run_scan_calls.append(p)  # type: ignore[method-assign]

                from PySide6.QtWidgets import QFileDialog

                QFileDialog.getExistingDirectory = staticmethod(  # type: ignore[assignment]
                    lambda *_a, **_k: td
                )
                window._on_browse_source()

                self.assertEqual(window._selected_source_path, td)
                self.assertEqual(run_scan_calls, [])
                self.assertTrue(window._scan_source_btn.isEnabled())
            finally:
                window.close()

    def test_scan_source_scans_selected_path(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                window._selected_source_path = td
                window._refresh_source_button_states()
                run_scan_calls: list[str] = []
                window._run_scan = lambda p: run_scan_calls.append(p)  # type: ignore[method-assign]
                stub_immediate_scan_launch(window, run_scan_calls)

                window._on_scan_source()

                self.assertEqual(run_scan_calls, [td])
            finally:
                window.close()

    def test_scan_disabled_when_no_source(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._selected_source_path = ""
                window._refresh_source_button_states()
                self.assertFalse(window._scan_source_btn.isEnabled())
                self.assertTrue(window._browse_source_btn.isEnabled())
            finally:
                window.close()

    def test_mode_switch_preserves_source_and_scan_stays_enabled(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                window._selected_source_path = td
                window._current_source = td
                window._update_source_label()
                window._refresh_source_button_states()

                idx = _combo_index_for(window, ASSET_MODE_IMAGES)
                window._search_mode_combo.setCurrentIndex(idx)

                self.assertEqual(window._selected_source_path, td)
                self.assertTrue(window._scan_source_btn.isEnabled())
            finally:
                window.close()

    def test_missing_source_shows_unavailable_browse_can_replace(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                missing = str(
                    Path(tempfile.gettempdir()) / f"missing-{uuid.uuid4().hex}"
                )
                window._selected_source_path = missing
                window._refresh_source_button_states()
                self.assertFalse(window._scan_source_btn.isEnabled())

                from PySide6.QtWidgets import QFileDialog

                QFileDialog.getExistingDirectory = staticmethod(  # type: ignore[assignment]
                    lambda *_a, **_k: td
                )
                window._on_browse_source()

                self.assertEqual(window._selected_source_path, td)
                self.assertTrue(window._scan_source_btn.isEnabled())
            finally:
                window.close()

    def test_persisted_source_restores_and_enables_scan(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            QSettings().setValue("paths/last_scan_folder", td)
            window = self._make_window()
            try:
                self.assertEqual(window._selected_source_path, td)
                self.assertTrue(window._scan_source_btn.isEnabled())
            finally:
                window.close()

    def test_scan_with_stale_path_opens_browse_not_direct_scan(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                missing = str(
                    Path(tempfile.gettempdir()) / f"gone-{uuid.uuid4().hex}"
                )
                window._selected_source_path = missing
                window._refresh_source_button_states()

                browse_calls: list[int] = []
                run_scan_calls: list[str] = []

                def _browse() -> None:
                    browse_calls.append(1)
                    window._persist_selected_source(td)

                window._on_browse_source = _browse  # type: ignore[method-assign]
                window._run_scan = lambda p: run_scan_calls.append(p)  # type: ignore[method-assign]

                window._on_scan_source()

                self.assertEqual(browse_calls, [1])
                self.assertEqual(run_scan_calls, [])
                self.assertEqual(window._selected_source_path, td)
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
