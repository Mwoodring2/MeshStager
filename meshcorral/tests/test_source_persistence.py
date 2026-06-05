"""Tests for Prime v0.7 source persistence + Asset Mode startup guard.

These tests focus on the behaviours that regressed after v0.7:

* The Asset Mode handler must not clear ``_current_source`` during construction /
  restore — only an *intentional* user mode change is allowed to wipe the source.
* The last scanned folder must be restored into the Source panel after launch.
* If the persisted folder no longer exists, the panel shows
  ``"Last source unavailable: <path>"`` instead of crashing or auto-clearing.

The tests build a real :class:`MainWindow` but use a private :class:`QSettings`
scope (``QCoreApplication.setApplicationName`` per-test) so they never write to
the user's real settings store.
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.app.config import ASSET_MODE_3D, ASSET_MODE_IMAGES


def _ensure_qapp() -> QApplication:
    """Return the singleton ``QApplication`` (created lazily for headless tests)."""
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst  # type: ignore[return-value]


class _SettingsSandbox:
    """Per-test QSettings scope to keep persisted state isolated."""

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

    def set_last_scan_folder(self, value: str) -> None:
        QSettings().setValue("paths/last_scan_folder", value)


class TestSourcePersistence(unittest.TestCase):
    """End-to-end source-restore behaviour on the real :class:`MainWindow`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        """Construct ``MainWindow`` against the active QSettings scope."""
        # Late import: building a MainWindow requires a QApplication.
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_existing_persisted_source_restored_into_label(self) -> None:
        """Existing folder → ``_selected_source_path`` is set, label shows the path.

        ``_current_source`` stays empty because no scan has run yet at restore time
        (Asset-Mode-switch fix: selection is decoupled from working rows).
        """
        with _SettingsSandbox() as sb, tempfile.TemporaryDirectory() as td:
            sb.set_last_scan_folder(td)
            window = self._make_window()
            try:
                self.assertEqual(window._selected_source_path, td)
                self.assertEqual(window._current_source, "")
                self.assertEqual(window._source_path_label.text(), td)
                self.assertFalse(window._is_initializing_ui)
            finally:
                window.close()

    def test_missing_persisted_source_shows_unavailable_banner(self) -> None:
        with _SettingsSandbox() as sb:
            missing = str(Path(tempfile.gettempdir()) / f"never-exists-{uuid.uuid4().hex}")
            sb.set_last_scan_folder(missing)
            window = self._make_window()
            try:
                self.assertEqual(window._current_source, "")
                self.assertIn(
                    "Last source unavailable",
                    window._source_path_label.text(),
                )
                self.assertIn(missing, window._source_path_label.text())
            finally:
                window.close()

    def test_no_persisted_source_keeps_default_label(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                self.assertEqual(window._current_source, "")
                self.assertEqual(
                    window._source_path_label.text(), "No source selected"
                )
            finally:
                window.close()

    def test_startup_mode_combo_change_does_not_clear_source(self) -> None:
        """A ``currentIndexChanged`` during init must not behave like a user switch."""
        with _SettingsSandbox() as sb, tempfile.TemporaryDirectory() as td:
            sb.set_last_scan_folder(td)
            window = self._make_window()
            try:
                window._is_initializing_ui = True
                window._selected_source_path = td
                window._current_source = td
                window._source_path_label.setText(td)
                window._all_records = [object()]
                window._view_records = list(window._all_records)

                idx_other = 1 if window._search_mode_combo.currentIndex() == 0 else 0
                window._search_mode_combo.setCurrentIndex(idx_other)

                self.assertEqual(window._selected_source_path, td)
                self.assertEqual(window._source_path_label.text(), td)
                self.assertTrue(window._all_records)
            finally:
                window.close()

    def test_user_mode_change_still_clears_view_and_source(self) -> None:
        with _SettingsSandbox() as sb, tempfile.TemporaryDirectory() as td:
            sb.set_last_scan_folder(td)
            window = self._make_window()
            try:
                window._current_source = td
                window._all_records = [object()]
                window._view_records = list(window._all_records)
                start_mode = window._asset_mode
                other = ASSET_MODE_IMAGES if start_mode == ASSET_MODE_3D else ASSET_MODE_3D
                # Locate combo index for `other` to trigger a real switch.
                idx_other = -1
                for i in range(window._search_mode_combo.count()):
                    if window._search_mode_combo.itemData(i) == other:
                        idx_other = i
                        break
                self.assertGreaterEqual(idx_other, 0)
                window._search_mode_combo.setCurrentIndex(idx_other)

                self.assertEqual(window._current_source, "")
                self.assertEqual(window._all_records, [])
                self.assertNotEqual(window._asset_mode, start_mode)
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
