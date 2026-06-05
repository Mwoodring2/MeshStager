"""RC hotfix: pre-worker scan cancel and SciPy native health."""

from __future__ import annotations

import unittest
import uuid
from unittest import mock

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.services.environment.native_renderer_health import (
    check_native_renderer_health,
    reset_native_renderer_health_cache,
)
from meshcorral.services.large_folder_scan_assessment import LargeFolderWarningPersistence
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.large_folder_warning_dialog import (
    LargeFolderWarningAction,
    LargeFolderWarningDialog,
    LargeFolderWarningResult,
)


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


class TestNativeRendererScipy(unittest.TestCase):
    def tearDown(self) -> None:
        reset_native_renderer_health_cache()

    def test_unavailable_when_scipy_missing(self) -> None:
        def fake_spec(name: str) -> object | None:
            if name == "scipy":
                return None
            return object()

        with mock.patch(
            "meshcorral.services.environment.native_renderer_health.importlib.util.find_spec",
            side_effect=fake_spec,
        ):
            reset_native_renderer_health_cache()
            health = check_native_renderer_health(force=True)
        self.assertFalse(health.available)
        self.assertIn("scipy", health.missing_dependencies)
        self.assertEqual(health.fallback_backend, "blender")
        self.assertIn("SciPy", health.settings_message)

    def test_requires_scipy_in_probe_list(self) -> None:
        """Native READY requires scipy alongside numpy, trimesh, and Pillow."""
        with mock.patch(
            "meshcorral.services.environment.native_renderer_health.importlib.util.find_spec",
            return_value=object(),
        ):
            reset_native_renderer_health_cache()
            health = check_native_renderer_health(force=True)
        self.assertTrue(health.available)
        self.assertEqual(health.missing_dependencies, ())


class TestLargeFolderDialogEsc(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_escape_rejects_dialog(self) -> None:
        from meshcorral.services.large_folder_scan_assessment import (
            FolderScopeEstimate,
            LargeFolderAssessment,
        )

        assessment = LargeFolderAssessment(
            source_path=r"\\srv\share",
            network_like=True,
            estimate=FolderScopeEstimate(
                matching_file_count=0,
                exceeds_file_threshold=False,
                archive_zip_count=0,
                max_directory_depth=0,
                preflight_truncated=True,
            ),
            prior_slow_folder=False,
            auto_thumbnails_enabled=True,
            prior_cached_count=0,
            would_use_lightweight=True,
            file_count_threshold=2500,
            thumbnail_mode_label="test",
            cache_mode_label="test",
        )
        dlg = LargeFolderWarningDialog(assessment)
        from PySide6.QtWidgets import QDialog

        dlg._esc_shortcut.activated.emit()
        self.assertEqual(dlg.result(), int(QDialog.DialogCode.Rejected))


class TestScanCancelBeforeWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_abort_before_worker_does_not_run_scan(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._scan_launch_pending = True
                window._scan_launch_generation = 1
                run_calls: list[str] = []
                window._run_scan = lambda p, **k: run_calls.append(p)  # type: ignore[method-assign]
                window._abort_scan_launch()
                window._deferred_run_scan_if_launched("C:/x", 1, mock.Mock())
                self.assertEqual(run_calls, [])
                self.assertTrue(window._scan_user_canceled_hint)
            finally:
                window.close()

    def test_confirm_async_cancel_invokes_on_done_false(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                outcomes: list[bool] = []

                def on_done(proceed: bool) -> None:
                    outcomes.append(proceed)

                with mock.patch.object(
                    window,
                    "_large_folder_persistence",
                ) as mock_persist, mock.patch(
                    "meshcorral.ui.main_window.build_large_folder_assessment",
                ) as mock_build:
                    mock_persist.return_value.should_show_warning.return_value = True
                    mock_build.return_value = mock.Mock(should_warn=True)
                    with mock.patch.object(
                        LargeFolderWarningDialog,
                        "open_dialog",
                        side_effect=lambda *a, **k: on_done(False) or mock.Mock(),
                    ):
                        result = window._confirm_large_folder_scan(
                            "C:/big", on_done=on_done
                        )
                self.assertIsNone(result)
                self.assertEqual(outcomes, [False])
            finally:
                window.close()

    def test_warning_dialog_continue_applies_overrides(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                outcomes: list[bool] = []
                result_payload = LargeFolderWarningResult(
                    action=LargeFolderWarningAction.SCAN_WITHOUT_THUMBNAILS,
                    skip_future_warnings=False,
                    skip_future_remote_only=False,
                    visible_thumbnails_only=True,
                    lightweight_scan=True,
                    background_metadata=True,
                )

                def on_done(proceed: bool) -> None:
                    outcomes.append(proceed)

                with mock.patch.object(
                    window, "_large_folder_persistence"
                ) as mock_persist, mock.patch(
                    "meshcorral.ui.main_window.build_large_folder_assessment",
                ) as mock_build:
                    mock_persist.return_value.should_show_warning.return_value = True
                    mock_build.return_value = mock.Mock(should_warn=True)

                    def fake_open(*_a, **k):
                        k["on_finished"](result_payload)
                        return mock.Mock()

                    with mock.patch.object(
                        LargeFolderWarningDialog, "open_dialog", side_effect=fake_open
                    ):
                        window._confirm_large_folder_scan("C:/big", on_done=on_done)
                self.assertEqual(outcomes, [True])
                self.assertTrue(window._scan_skip_auto_thumbnails_once)
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
