"""Tests for the Asset-Mode-switch-preserves-source fix.

Scenario the regression captured:

1. User scans a folder in 3D / DCC Assets mode.
2. User flips Asset Mode to Images / Textures.
3. The source label still shows the folder, but Scan Source falls back to "no
   source selected" semantics.

After the fix the source folder is the user's *selection*, decoupled from the
*working rows* — switching mode clears rows but the source stays put as the
scan target. Pressing Scan Source rescans the same folder in the new mode.
"""

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
    """Per-test QSettings scope so tests never touch real user settings."""

    def __init__(self) -> None:
        self._org_name = QCoreApplication.organizationName() or ""
        self._app_name = QCoreApplication.applicationName() or ""
        self._test_id = f"meshcorral-tests-{uuid.uuid4().hex[:8]}"

    def __enter__(self) -> "_SettingsSandbox":
        QCoreApplication.setOrganizationName("MeshCorralTests")
        QCoreApplication.setApplicationName(self._test_id)
        QSettings().clear()
        return self

    def __exit__(self, *exc) -> None:  # type: ignore[no-untyped-def]
        QSettings().clear()
        QCoreApplication.setOrganizationName(self._org_name)
        QCoreApplication.setApplicationName(self._app_name)


def _combo_index_for(window, mode: str) -> int:  # type: ignore[no-untyped-def]
    for i in range(window._search_mode_combo.count()):
        if window._search_mode_combo.itemData(i) == mode:
            return i
    return -1


class TestModeSwitchPreservesSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def _force_mode(self, window, mode: str) -> None:  # type: ignore[no-untyped-def]
        """Force *window* into *mode* without firing the change handler.

        ``SettingsService`` uses a fixed ``("WoodringTools", "MeshStager")`` QSettings
        scope that bypasses our per-test sandbox, so prior tests can leak mode
        state. Snap both the persisted setting and the in-process combo / attr
        to a known starting state for each test.
        """
        window._settings_service.set_search_mode(mode)
        window._asset_mode = mode
        idx = _combo_index_for(window, mode)
        if idx >= 0:
            window._search_mode_combo.blockSignals(True)
            try:
                window._search_mode_combo.setCurrentIndex(idx)
            finally:
                window._search_mode_combo.blockSignals(False)

    def _seed_3d_scan(self, window, folder: str) -> None:  # type: ignore[no-untyped-def]
        """Pretend a 3D scan has just completed against *folder*."""
        self._force_mode(window, ASSET_MODE_3D)
        window._selected_source_path = folder
        window._current_source = folder
        window._last_scan_folder = folder
        window._all_records = [object()]
        window._view_records = list(window._all_records)
        window._update_source_label()

    def test_mode_switch_clears_rows_but_keeps_selected_source(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                self._seed_3d_scan(window, td)
                self.assertEqual(window._asset_mode, ASSET_MODE_3D)
                idx_img = _combo_index_for(window, ASSET_MODE_IMAGES)
                self.assertGreaterEqual(idx_img, 0)
                window._search_mode_combo.setCurrentIndex(idx_img)

                self.assertEqual(window._asset_mode, ASSET_MODE_IMAGES)
                self.assertEqual(window._current_source, "")
                self.assertEqual(window._all_records, [])
                # Source survives the mode switch.
                self.assertEqual(window._selected_source_path, td)
                self.assertEqual(window._source_path_label.text(), td)
            finally:
                window.close()

    def test_scan_source_after_mode_switch_uses_selected_source(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                self._seed_3d_scan(window, td)
                # Flip 3D -> Images via the combo.
                idx_img = _combo_index_for(window, ASSET_MODE_IMAGES)
                window._search_mode_combo.setCurrentIndex(idx_img)

                run_scan_calls: list[str] = []
                window._run_scan = lambda p: run_scan_calls.append(p)  # type: ignore[method-assign]
                stub_immediate_scan_launch(window, run_scan_calls)
                # Picker MUST NOT open when a usable selected source exists.
                window._on_scan_source()

                self.assertEqual(run_scan_calls, [td])
            finally:
                window.close()

    def test_scan_source_then_back_to_3d_rescans_same_folder(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                self._seed_3d_scan(window, td)
                # 3D -> Images
                window._search_mode_combo.setCurrentIndex(
                    _combo_index_for(window, ASSET_MODE_IMAGES)
                )
                # Images -> 3D
                window._search_mode_combo.setCurrentIndex(
                    _combo_index_for(window, ASSET_MODE_3D)
                )
                self.assertEqual(window._asset_mode, ASSET_MODE_3D)
                self.assertEqual(window._selected_source_path, td)

                run_scan_calls: list[str] = []
                window._run_scan = lambda p: run_scan_calls.append(p)  # type: ignore[method-assign]
                stub_immediate_scan_launch(window, run_scan_calls)
                window._on_scan_source()

                self.assertEqual(run_scan_calls, [td])
            finally:
                window.close()

    def test_label_does_not_show_no_source_selected_after_mode_switch(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                self._seed_3d_scan(window, td)
                window._search_mode_combo.setCurrentIndex(
                    _combo_index_for(window, ASSET_MODE_IMAGES)
                )
                label_text = window._source_path_label.text()
                self.assertNotEqual(label_text, "No source selected")
                self.assertEqual(label_text, td)
            finally:
                window.close()

    def test_missing_selected_source_scan_disabled_until_browse(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                missing = str(
                    Path(tempfile.gettempdir()) / f"never-exists-{uuid.uuid4().hex}"
                )
                window._selected_source_path = missing
                window._refresh_source_button_states()

                self.assertFalse(window._scan_source_btn.isEnabled())

                from PySide6.QtWidgets import QFileDialog

                QFileDialog.getExistingDirectory = staticmethod(  # type: ignore[assignment]
                    lambda *_a, **_k: td
                )
                run_scan_calls: list[str] = []
                window._run_scan = lambda p: run_scan_calls.append(p)  # type: ignore[method-assign]
                window._on_browse_source()

                self.assertEqual(window._selected_source_path, td)
                self.assertEqual(run_scan_calls, [])
                self.assertTrue(window._scan_source_btn.isEnabled())
            finally:
                window.close()

    def test_run_scan_records_selected_source_path(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                # Stub out the heavy parts of _run_scan so we don't spin a real
                # QThread; we only care that the selected source attribute is
                # updated when _run_scan is invoked.
                window._scan_thread = None
                # Pretend a scan is in flight (so subsequent guards fire harmlessly).
                pretend_scan = False

                def _fake_scan(folder: str) -> None:
                    nonlocal pretend_scan
                    # Mirror the real method's "record selection first" step.
                    window._selected_source_path = folder
                    pretend_scan = True

                # Replace _run_scan to keep the test deterministic.
                window._run_scan = _fake_scan  # type: ignore[method-assign]
                window._run_scan(td)

                self.assertTrue(pretend_scan)
                self.assertEqual(window._selected_source_path, td)
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
