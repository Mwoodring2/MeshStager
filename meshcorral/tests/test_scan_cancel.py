"""Tests for cooperative folder scan cancellation (Esc) and scan startup responsiveness."""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication, QSettings, QThread
from PySide6.QtWidgets import QApplication

from meshcorral.services.large_folder_scan_assessment import (
    build_large_folder_assessment,
    network_preflight_scope_estimate,
    preflight_folder_scope,
)
from meshcorral.services.scan_cancel import ScanCancelToken
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.large_folder_scan_assessment import LargeFolderWarningPersistence
from meshcorral.ui.empty_states import SCAN_CANCELED
from meshcorral.ui.footer_status import (
    format_scan_cancel_pending_footer,
    format_scan_footer,
    format_scan_still_scanning_footer,
    status_canceling_scan,
    status_scan_canceled,
)
from meshcorral.ui.scan_runner import FolderScanRunner
from meshcorral.ui.scan_startup_timing import LOG_PREFIX, ScanStartupTimer


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


class TestScanCancelToken(unittest.TestCase):
    def test_request_cancel_sets_flag(self) -> None:
        token = ScanCancelToken()
        self.assertFalse(token.is_canceled())
        token.request_cancel()
        self.assertTrue(token.is_canceled())


class TestScanRunnerCancel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_canceled_emit_never_raises(self) -> None:
        class _RaisingSignal:
            def emit(self, *_a: object, **_k: object) -> None:
                raise RuntimeError("deleted")

        runner = FolderScanRunner()
        runner.scan_canceled = _RaisingSignal()  # type: ignore[assignment]
        runner._safe_emit_canceled(0.1, 3)


class TestScanStartupTiming(unittest.TestCase):
    def test_timer_logs_without_raising(self) -> None:
        timer = ScanStartupTimer()
        with self.assertLogs("meshcorral.ui.scan_startup_timing", level="INFO") as captured:
            timer.mark("TEST_STEP")
        joined = "\n".join(captured.output)
        self.assertIn(LOG_PREFIX, joined)
        self.assertIn("TEST_STEP", joined)


class TestNetworkPreflightSkip(unittest.TestCase):
    def test_build_skips_deep_preflight_on_network(self) -> None:
        with mock.patch(
            "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
            return_value=True,
        ), mock.patch(
            "meshcorral.services.large_folder_scan_assessment.preflight_folder_scope",
        ) as mock_preflight:
            assessment = build_large_folder_assessment(
                r"\\holocron\Photos\assets",
                recursive=True,
                allowed_extensions={".stl"},
                settings_service=SettingsService(),
                persistence=LargeFolderWarningPersistence(QSettings()),
                prior_cached_count=0,
            )
            mock_preflight.assert_not_called()
        self.assertIn("network_path", assessment.trigger_reasons())
        self.assertTrue(assessment.estimate.preflight_truncated)

    def test_local_still_uses_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.stl").write_bytes(b"x")
            with mock.patch(
                "meshcorral.services.large_folder_scan_assessment.is_network_like_path",
                return_value=False,
            ):
                est = preflight_folder_scope(
                    root,
                    recursive=False,
                    allowed_extensions={".stl"},
                )
            self.assertEqual(est.matching_file_count, 1)

    def test_network_estimate_is_placeholder(self) -> None:
        est = network_preflight_scope_estimate()
        self.assertEqual(est.matching_file_count, 0)
        self.assertFalse(est.exceeds_file_threshold)


class TestScanCancelFooterCopy(unittest.TestCase):
    def test_scan_footer_includes_esc_hint(self) -> None:
        text = format_scan_footer(files_found=10, folder_hint="models")
        self.assertIn("Press Esc to cancel", text)
        self.assertIn("10 files found", text)

    def test_still_scanning_footer_esc_hint(self) -> None:
        text = format_scan_still_scanning_footer(files_found=340)
        self.assertIn("Still scanning", text)
        self.assertIn("340", text)
        self.assertIn("Press Esc to cancel", text)

    def test_cancel_pending_footer(self) -> None:
        self.assertEqual(format_scan_cancel_pending_footer(), "Canceling scan…")
        self.assertEqual(status_canceling_scan(), "Canceling scan…")
        self.assertEqual(status_scan_canceled(), "Scan canceled.")


class TestMainWindowScanCancel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_no_cancel_scan_button_in_source_panel(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                self.assertFalse(hasattr(window, "_cancel_scan_btn"))
            finally:
                window.close()

    def test_escape_during_scan_requests_cancel(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._is_scanning = True
                window._scan_cancel_pending = False
                window._scan_cancel_token = ScanCancelToken()
                window._request_scan_cancel()
                self.assertTrue(window._scan_cancel_pending)
                self.assertTrue(window._scan_cancel_token.is_canceled())
            finally:
                window.close()

    def test_repeated_escape_while_cancel_pending_does_not_spam(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._is_scanning = True
                window._scan_cancel_pending = True
                window._scan_cancel_token = ScanCancelToken()
                window._request_scan_cancel()
                self.assertFalse(window._scan_cancel_token.is_canceled())
                window._on_escape_cancel_scan()
                self.assertFalse(window._scan_cancel_token.is_canceled())
            finally:
                window.close()

    def test_request_scan_cancel_never_waits_on_thread(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                thr = mock.MagicMock(spec=QThread)
                thr.isRunning.return_value = True
                window._scan_thread = thr
                window._is_scanning = True
                window._scan_cancel_token = ScanCancelToken()
                window._request_scan_cancel()
                thr.wait.assert_not_called()
            finally:
                window.close()

    def test_cancel_enrichment_does_not_wait_on_ui_thread(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                thr = mock.MagicMock(spec=QThread)
                thr.isRunning.return_value = True
                window._enrichment_thread = thr
                window._cancel_active_enrichment()
                thr.wait.assert_not_called()
            finally:
                window.close()

    def test_canceled_scan_does_not_enqueue_thumbnails(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                with mock.patch.object(
                    window, "_schedule_auto_thumbnails_after_scan"
                ) as mock_thumbs, mock.patch.object(
                    window, "_schedule_metadata_enrichment_after_scan"
                ) as mock_enrich, mock.patch.object(
                    window, "_deferred_refresh_thumb_index_after_scan"
                ):
                    window._scan_accept_events = True
                    window._is_scanning = True
                    window._pending_scan_path = "C:/src"
                    window._selected_source_path = "C:/src"
                    window._all_records = []
                    window._on_scan_worker_canceled(0.5, 0)
                mock_thumbs.assert_not_called()
                mock_enrich.assert_not_called()
            finally:
                window.close()

    def test_canceled_scan_preserves_selected_source_path(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                window._scan_accept_events = True
                window._is_scanning = True
                window._pending_scan_path = td
                window._selected_source_path = td
                window._all_records = []
                window._pre_scan_backup_records = []
                window._pre_scan_backup_source = ""
                window._on_scan_worker_canceled(0.2, 0)
                self.assertEqual(window._selected_source_path, td)
            finally:
                window.close()

    def test_scan_canceled_empty_state_and_status(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                from meshcorral.ui.empty_states import empty_state_spec

                window._scan_accept_events = True
                window._is_scanning = True
                window._pending_scan_path = "C:/missing"
                window._selected_source_path = "C:/missing"
                window._current_source = ""
                window._all_records = []
                window._on_scan_worker_canceled(0.1, 0)
                self.assertTrue(window._scan_user_canceled_hint)
                spec = empty_state_spec(SCAN_CANCELED)
                self.assertIn(spec.title, window._source_mode_hint.text())
                self.assertFalse(window._is_scanning)
            finally:
                window.close()

    def test_controls_reenable_after_cancel_completion(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                window._selected_source_path = td
                window._scan_accept_events = True
                window._is_scanning = True
                window._pending_scan_path = td
                window._all_records = []
                window._on_scan_worker_canceled(0.1, 0)
                window._update_ui_state()
                self.assertFalse(window._is_scanning)
                self.assertTrue(window._scan_source_btn.isEnabled())
            finally:
                window.close()

    def test_stale_scan_batch_after_cancel_is_ignored(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                from meshcorral.models.file_record import FileRecord

                window._scan_accept_events = False
                window._scan_cancel_pending = False
                window._all_records = []
                window._view_records = []
                window._model.set_rows([])
                window._gallery_model.set_records([])
                rec = FileRecord(
                    path=Path("C:/x/a.stl"),
                    name="a.stl",
                    extension=".stl",
                    parent_folder="x",
                )
                window._on_scan_worker_batch([rec])
                self.assertEqual(len(window._all_records), 0)
            finally:
                window.close()

    def test_finished_ok_after_cancel_accept_flag_cleared_is_ignored(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._scan_accept_events = False
                window._is_scanning = False
                with mock.patch.object(
                    window, "_schedule_auto_thumbnails_after_scan"
                ) as mock_thumbs:
                    window._on_scan_worker_finished_ok(1.0, 5)
                mock_thumbs.assert_not_called()
            finally:
                window.close()

    def test_scanning_footer_while_active(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._is_scanning = True
                window._scan_cancel_pending = False
                window._last_scan_progress_folder = ""
                text = window._scan_status_while_walking(0)
                self.assertIn("Press Esc to cancel", text)
                stale = window._scan_status_while_walking(5, still_scanning=True)
                self.assertIn("Still scanning", stale)
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
