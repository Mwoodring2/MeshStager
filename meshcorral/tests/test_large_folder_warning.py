"""Tests for large-folder / server-folder scan warnings."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.services.large_folder_scan_assessment import (
    DEFAULT_FILE_COUNT_WARNING_THRESHOLD,
    LargeFolderWarningPersistence,
    build_large_folder_assessment,
    network_preflight_scope_estimate,
    preflight_folder_scope,
    recommended_dialog_defaults,
    slow_folder_key,
)
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.large_folder_warning_dialog import (
    LargeFolderWarningAction,
    LargeFolderWarningDialog,
    LargeFolderWarningResult,
)
from meshcorral.utils.path_perf import is_network_like_path


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


class TestLargeFolderAssessment(unittest.TestCase):
    def test_unc_path_triggers_network_reason(self) -> None:
        path = Path(r"\\server\share\assets")
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
            return_value=True,
        ), mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            assessment = build_large_folder_assessment(
                str(path),
                recursive=False,
                allowed_extensions={".stl"},
                settings_service=SettingsService(),
                persistence=LargeFolderWarningPersistence(QSettings()),
                prior_cached_count=0,
            )
            mock_preflight.assert_not_called()
        self.assertIn("network_path", assessment.trigger_reasons())
        self.assertEqual(assessment.estimate.matching_file_count, 0)

    def test_network_preflight_placeholder(self) -> None:
        est = network_preflight_scope_estimate()
        self.assertTrue(est.preflight_truncated)
        self.assertEqual(est.matching_file_count, 0)

    def test_huge_file_count_triggers_large_file_count(self) -> None:
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            from meshcorral.services.large_folder_scan_assessment import FolderScopeEstimate

            mock_preflight.return_value = FolderScopeEstimate(
                matching_file_count=3000,
                exceeds_file_threshold=True,
                archive_zip_count=0,
                max_directory_depth=2,
                preflight_truncated=True,
            )
            assessment = build_large_folder_assessment(
                "C:/big",
                recursive=True,
                allowed_extensions={".stl"},
                settings_service=SettingsService(),
                persistence=LargeFolderWarningPersistence(QSettings()),
                prior_cached_count=0,
            )
        self.assertIn("large_file_count", assessment.trigger_reasons())

    def test_preflight_counts_matching_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(5):
                (root / f"m{i}.stl").write_bytes(b"x")
            (root / "skip.txt").write_text("nope", encoding="utf-8")
            est = preflight_folder_scope(
                root,
                recursive=False,
                allowed_extensions={".stl"},
                file_count_threshold=100,
            )
        self.assertEqual(est.matching_file_count, 5)
        self.assertFalse(est.exceeds_file_threshold)

    def test_skip_all_persistence(self) -> None:
        settings = QSettings("WoodringToolsTest", "RoundupLargeFolder")
        settings.clear()
        persistence = LargeFolderWarningPersistence(settings)
        persistence.set_skip_all_warnings(True)
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            from meshcorral.services.large_folder_scan_assessment import FolderScopeEstimate

            mock_preflight.return_value = FolderScopeEstimate(
                matching_file_count=5000,
                exceeds_file_threshold=True,
                archive_zip_count=0,
                max_directory_depth=1,
                preflight_truncated=True,
            )
            assessment = build_large_folder_assessment(
                r"\\srv\lib",
                recursive=True,
                allowed_extensions={".stl"},
                settings_service=SettingsService(settings),
                persistence=persistence,
                prior_cached_count=0,
            )
        self.assertTrue(assessment.should_warn)
        self.assertFalse(persistence.should_show_warning(assessment))

    def test_skip_remote_only_leaves_local_warn(self) -> None:
        settings = QSettings("WoodringToolsTest", "RoundupLargeFolder2")
        settings.clear()
        persistence = LargeFolderWarningPersistence(settings)
        persistence.set_skip_remote_only(True)
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
            return_value=True,
        ), mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            from meshcorral.services.large_folder_scan_assessment import FolderScopeEstimate

            mock_preflight.return_value = FolderScopeEstimate(
                matching_file_count=100,
                exceeds_file_threshold=False,
                archive_zip_count=0,
                max_directory_depth=1,
                preflight_truncated=False,
            )
            remote = build_large_folder_assessment(
                r"\\srv\lib",
                recursive=False,
                allowed_extensions={".stl"},
                settings_service=SettingsService(settings),
                persistence=persistence,
                prior_cached_count=0,
            )
        self.assertFalse(persistence.should_show_warning(remote))

    def test_slow_folder_registry(self) -> None:
        settings = QSettings("WoodringToolsTest", "RoundupSlow")
        settings.clear()
        persistence = LargeFolderWarningPersistence(settings)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp).resolve())
            persistence.record_scan_telemetry(
                source_path=path,
                scan_duration_s=12.0,
                file_count=400,
                network_like=False,
                thumbnail_queued=3,
                cancelled=False,
            )
            self.assertTrue(persistence.is_slow_folder(path))
            self.assertEqual(slow_folder_key(path), slow_folder_key(path))

    def test_recommended_defaults_network(self) -> None:
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
            return_value=True,
        ), mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            from meshcorral.services.large_folder_scan_assessment import FolderScopeEstimate

            mock_preflight.return_value = FolderScopeEstimate(
                matching_file_count=10,
                exceeds_file_threshold=False,
                archive_zip_count=0,
                max_directory_depth=1,
                preflight_truncated=False,
            )
            assessment = build_large_folder_assessment(
                r"\\srv\share",
                recursive=False,
                allowed_extensions={".stl"},
                settings_service=SettingsService(),
                persistence=LargeFolderWarningPersistence(QSettings()),
                prior_cached_count=0,
            )
        visible, lightweight, _bg = recommended_dialog_defaults(assessment)
        self.assertTrue(visible)
        # Network scans already use lightweight; recommendation only enables when not active.
        self.assertFalse(lightweight)
        self.assertTrue(assessment.would_use_lightweight)
        dlg = LargeFolderWarningDialog(assessment, parent=None)
        self.assertTrue(dlg._lightweight_check.isChecked())

    def test_auto_thumbs_on_remote_trigger(self) -> None:
        svc = SettingsService()
        svc.set_auto_thumbnail_after_scan(True)
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
            return_value=True,
        ), mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            from meshcorral.services.large_folder_scan_assessment import FolderScopeEstimate

            mock_preflight.return_value = FolderScopeEstimate(
                matching_file_count=1,
                exceeds_file_threshold=False,
                archive_zip_count=0,
                max_directory_depth=0,
                preflight_truncated=False,
            )
            assessment = build_large_folder_assessment(
                r"\\srv\a",
                recursive=False,
                allowed_extensions={".stl"},
                settings_service=svc,
                persistence=LargeFolderWarningPersistence(QSettings()),
                prior_cached_count=0,
            )
        self.assertIn("auto_thumbs_on_remote", assessment.trigger_reasons())


class TestLargeFolderWarningDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_dialog_continue_result(self) -> None:
        assessment = self._sample_assessment(network=True)
        dlg = LargeFolderWarningDialog(assessment, parent=None)
        dlg._result_action = LargeFolderWarningAction.CONTINUE
        dlg._visible_thumbs_check.setChecked(True)
        dlg._lightweight_check.setChecked(True)
        dlg.accept()
        result = dlg.result_value()
        self.assertEqual(result.action, LargeFolderWarningAction.CONTINUE)
        self.assertTrue(result.visible_thumbnails_only)
        self.assertTrue(result.lightweight_scan)

    def test_dialog_scan_without_thumbnails(self) -> None:
        assessment = self._sample_assessment(network=False)
        dlg = LargeFolderWarningDialog(assessment, parent=None)
        dlg._accept_no_thumbs()
        result = dlg.result_value()
        self.assertEqual(result.action, LargeFolderWarningAction.SCAN_WITHOUT_THUMBNAILS)

    @staticmethod
    def _sample_assessment(*, network: bool) -> object:
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
            return_value=network,
        ), mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            from meshcorral.services.large_folder_scan_assessment import FolderScopeEstimate

            mock_preflight.return_value = FolderScopeEstimate(
                matching_file_count=3000,
                exceeds_file_threshold=True,
                archive_zip_count=0,
                max_directory_depth=3,
                preflight_truncated=True,
            )
            return build_large_folder_assessment(
                r"\\srv\lib" if network else "C:/lib",
                recursive=True,
                allowed_extensions={".stl"},
                settings_service=SettingsService(),
                persistence=LargeFolderWarningPersistence(QSettings()),
                prior_cached_count=0,
            )


class TestMainWindowLargeFolderFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_confirm_cancel_aborts_scan(self) -> None:
        from meshcorral.ui.main_window import MainWindow

        window = MainWindow()
        window._selected_source_path = "C:/fake"
        with mock.patch.object(window, "_selected_source_is_valid", return_value=True), mock.patch.object(
            window,
            "_confirm_large_folder_scan",
            return_value=False,
        ) as mock_confirm, mock.patch.object(window, "_run_scan") as mock_run:
            window._on_scan_source()
        mock_confirm.assert_called_once()
        mock_run.assert_not_called()

    def test_confirm_continue_runs_scan(self) -> None:
        from meshcorral.ui.main_window import MainWindow

        window = MainWindow()
        window._selected_source_path = "C:/fake"
        def _confirm_ok(*_a, on_done=None, **_k):
            if on_done is not None:
                on_done(True)
            return True

        with mock.patch.object(window, "_selected_source_is_valid", return_value=True), mock.patch.object(
            window,
            "_confirm_large_folder_scan",
            side_effect=_confirm_ok,
        ), mock.patch.object(window, "_run_scan") as mock_run:
            window._on_scan_source()
            QCoreApplication.processEvents()
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0], "C:/fake")

    def test_scan_without_thumbnails_sets_override(self) -> None:
        from meshcorral.ui.main_window import MainWindow

        window = MainWindow()
        result = LargeFolderWarningResult(
            action=LargeFolderWarningAction.SCAN_WITHOUT_THUMBNAILS,
            skip_future_warnings=False,
            skip_future_remote_only=False,
            visible_thumbnails_only=False,
            lightweight_scan=False,
            background_metadata=True,
        )
        with mock.patch.object(
            LargeFolderWarningDialog,
            "run_dialog",
            return_value=result,
        ), mock.patch.object(
            window,
            "_large_folder_persistence",
        ) as mock_persist:
            mock_persist.return_value.should_show_warning.return_value = True
            with mock.patch(
                "meshcorral.ui.main_window.build_large_folder_assessment",
            ) as mock_build:
                mock_build.return_value.should_warn = True
                ok = window._confirm_large_folder_scan("C:/x")
        self.assertTrue(ok)
        self.assertTrue(window._scan_skip_auto_thumbnails_once)

    def test_lightweight_override_from_dialog(self) -> None:
        from meshcorral.ui.main_window import MainWindow

        window = MainWindow()
        result = LargeFolderWarningResult(
            action=LargeFolderWarningAction.CONTINUE,
            skip_future_warnings=False,
            skip_future_remote_only=False,
            visible_thumbnails_only=True,
            lightweight_scan=True,
            background_metadata=True,
        )
        with mock.patch.object(
            LargeFolderWarningDialog,
            "run_dialog",
            return_value=result,
        ), mock.patch.object(
            window,
            "_large_folder_persistence",
        ) as mock_persist, mock.patch(
            "meshcorral.ui.main_window.build_large_folder_assessment",
        ) as mock_build:
            mock_persist.return_value.should_show_warning.return_value = True
            mock_build.return_value.should_warn = True
            window._confirm_large_folder_scan(r"\\srv\share")
        self.assertTrue(window._scan_force_lightweight_once)
        self.assertTrue(window._scan_visible_thumbs_only_once)


class TestPathPerfUnc(unittest.TestCase):
    def test_unc_is_network_like(self) -> None:
        self.assertTrue(is_network_like_path(Path(r"\\server\share\folder")))


if __name__ == "__main__":
    unittest.main()
