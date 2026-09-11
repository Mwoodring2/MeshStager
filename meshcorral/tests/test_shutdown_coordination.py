"""Tests for the deterministic shutdown coordinator (pre-Prime v0.8).

These tests cover three layers:

* ``ThumbnailViewController.request_shutdown()`` and its slot guards.
* ``BridgeQueueManager.shutdown()`` re-entry / state contract.
* ``MainWindow`` shutdown driver (``_shutdown_app``) — flag, no-op enqueue paths,
  worker cancellation calls, and idempotency.

The MainWindow tests use a private QSettings scope so they never write to the
user's real settings store.
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.thumbnail_controller import ThumbnailViewController


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst  # type: ignore[return-value]


def _rec(path: Path) -> FileRecord:
    return FileRecord(
        path=path,
        name=path.name,
        extension=path.suffix.lower(),
        parent_folder=path.parent.name,
    )


class _SettingsSandbox:
    """Per-test QSettings scope so tests never write to the user's real store."""

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


class TestThumbnailControllerShutdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_request_shutdown_sets_flag_and_clears_inflight(self) -> None:
        ctrl = ThumbnailViewController()
        with tempfile.TemporaryDirectory() as td:
            rec = _rec(Path(td) / "a.png")
            key = _norm_path_key(rec.path)
            cache_key = ctrl._pixmap_cache_key(key, ctrl.display_pixel_size())
            ctrl._decoding_keys.add(cache_key)
            ctrl.request_shutdown(timeout_ms=10)
            self.assertTrue(ctrl.is_shutting_down())
            self.assertEqual(len(ctrl._decoding_keys), 0)

    def test_request_shutdown_is_idempotent(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.request_shutdown(timeout_ms=10)
        # A second call must not raise.
        ctrl.request_shutdown(timeout_ms=10)
        self.assertTrue(ctrl.is_shutting_down())

    def test_start_decode_noop_after_shutdown(self) -> None:
        ctrl = ThumbnailViewController()
        calls: list[object] = []
        ctrl._pool.start = lambda r: calls.append(r)  # type: ignore[method-assign]
        ctrl.request_shutdown(timeout_ms=10)
        ctrl._start_decode("k", "C:/x.png", px=96, purpose="gallery")
        self.assertEqual(calls, [])
        self.assertEqual(len(ctrl._decoding_keys), 0)

    def test_prime_raster_ready_noop_after_shutdown(self) -> None:
        ctrl = ThumbnailViewController()
        starts: list[object] = []
        ctrl._primer_pool.start = lambda r: starts.append(r)  # type: ignore[method-assign]
        ctrl.request_shutdown(timeout_ms=10)
        with tempfile.TemporaryDirectory() as td:
            ctrl.prime_raster_ready_async([_rec(Path(td) / "a.png")])
        self.assertEqual(starts, [])

    def test_on_image_ready_noop_after_shutdown(self) -> None:
        ctrl = ThumbnailViewController()
        refreshes: list[str] = []
        ctrl._request_row_refresh = lambda k: refreshes.append(k)  # type: ignore[method-assign]
        ctrl.request_shutdown(timeout_ms=10)
        ctrl._on_image_ready("gallery", "k", "C:/x.png", None)
        self.assertEqual(refreshes, [])

    def test_on_image_stale_noop_after_shutdown(self) -> None:
        ctrl = ThumbnailViewController()
        before = ctrl.stale_drop_count()
        ctrl.request_shutdown(timeout_ms=10)
        ctrl._on_image_stale("gallery", "k", 96)
        # Counter must not advance because the slot bailed out.
        self.assertEqual(ctrl.stale_drop_count(), before)

    def test_on_raster_paths_ready_noop_after_shutdown(self) -> None:
        ctrl = ThumbnailViewController()
        marks: list[Path] = []
        ctrl._ready_cache.mark_ready_raster = lambda p: marks.append(p) or True  # type: ignore[method-assign]
        ctrl.request_shutdown(timeout_ms=10)
        with tempfile.TemporaryDirectory() as td:
            ctrl._on_raster_paths_ready([Path(td) / "x.png"])
        self.assertEqual(marks, [])


class TestBridgeQueueManagerShutdown(unittest.TestCase):
    def test_shutdown_flag_set_and_idempotent(self) -> None:
        from meshcorral.app.bridge.queue_manager import BridgeQueueManager
        from meshcorral.services.settings_service import SettingsService

        with _SettingsSandbox():
            mgr = BridgeQueueManager(SettingsService())
            try:
                self.assertFalse(mgr.is_shutting_down())
                mgr.shutdown(timeout=0.5)
                self.assertTrue(mgr.is_shutting_down())
                # Re-entry must be safe.
                mgr.shutdown(timeout=0.5)
            finally:
                # Already shut down; this is a no-op but guarantees test isolation.
                mgr.shutdown(timeout=0.5)

    def test_request_stop_and_cancel_pending(self) -> None:
        from meshcorral.app.bridge.queue_manager import BridgeQueueManager
        from meshcorral.services.settings_service import SettingsService

        with _SettingsSandbox():
            mgr = BridgeQueueManager(SettingsService())
            try:
                mgr.request_stop()
                self.assertTrue(mgr.is_shutting_down())
                self.assertEqual(mgr.pending_count(), 0)
                self.assertEqual(mgr.active_count(), 0)
            finally:
                mgr.shutdown(timeout=0.5)

    def test_enqueue_rejected_after_request_stop(self) -> None:
        from meshcorral.app.bridge.queue_manager import BridgeQueueManager
        from meshcorral.services.settings_service import SettingsService

        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            mesh = Path(td) / "m.fbx"
            mesh.write_text("fbx")
            mgr = BridgeQueueManager(SettingsService())
            try:
                with patch(
                    "meshcorral.app.bridge.queue_manager.find_blender_executable",
                    return_value=Path(td) / "blender.exe",
                ):
                    (Path(td) / "blender.exe").write_text("")
                    mgr.request_stop()
                    ok, msg, _reject = mgr.try_enqueue_thumbnail(mesh)
                self.assertFalse(ok)
                self.assertIn("shutting down", msg.lower())
            finally:
                mgr.shutdown(timeout=0.5)


class TestMainWindowShutdownCoordinator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_shutdown_app_sets_flag_and_invokes_workers(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                calls: dict[str, int] = {
                    "thumb": 0,
                    "bridge_shutdown": 0,
                    "bridge_cancel": 0,
                    "bridge_stop": 0,
                    "enrich": 0,
                    "enrich_wait_ms": 0,
                    "disconnect_bridge": 0,
                }

                def _thumb_stop(*, timeout_ms: int = 1500) -> None:
                    calls["thumb"] += 1

                def _bridge_shutdown(timeout: float = 1.0, **kwargs: object) -> None:
                    calls["bridge_shutdown"] += 1

                def _bridge_cancel() -> int:
                    calls["bridge_cancel"] += 1
                    return 0

                def _bridge_stop() -> None:
                    calls["bridge_stop"] += 1

                def _cancel_enrich(*, wait_ms: int = 0) -> None:
                    # Shutdown passes a bounded join; interactive cancels pass nothing.
                    calls["enrich"] += 1
                    calls["enrich_wait_ms"] = int(wait_ms)

                def _disconnect_bridge() -> None:
                    calls["disconnect_bridge"] += 1

                window._thumb_controller.request_shutdown = _thumb_stop  # type: ignore[assignment]
                window._bridge_queue.shutdown = _bridge_shutdown  # type: ignore[assignment]
                window._bridge_queue.request_stop = _bridge_stop  # type: ignore[assignment]
                window._bridge_queue.cancel_pending = _bridge_cancel  # type: ignore[assignment]
                window._bridge_queue.pending_count = lambda: 0  # type: ignore[assignment]
                window._bridge_queue.active_count = lambda: 0  # type: ignore[assignment]
                window._cancel_active_enrichment = _cancel_enrich  # type: ignore[assignment]
                window._disconnect_bridge_ui_signals = _disconnect_bridge  # type: ignore[assignment]

                window._shutdown_app(reason="test")

                self.assertTrue(window._shutting_down)
                self.assertEqual(calls["thumb"], 1)
                self.assertEqual(calls["bridge_shutdown"], 1)
                self.assertEqual(calls["bridge_cancel"], 1)
                self.assertEqual(calls["bridge_stop"], 1)
                self.assertEqual(calls["enrich"], 1)
                self.assertGreater(
                    calls["enrich_wait_ms"],
                    0,
                    "shutdown must join the enrichment thread before the window is destroyed",
                )
                self.assertEqual(calls["disconnect_bridge"], 1)
            finally:
                window.close()

    def test_close_event_logs_initiated_and_complete(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._shutdown_app = lambda *, reason: None  # type: ignore[assignment]
                with self.assertLogs("meshcorral.ui.main_window", level="INFO") as captured:
                    from PySide6.QtGui import QCloseEvent

                    event = QCloseEvent()
                    window.closeEvent(event)
                joined = "\n".join(captured.output)
                self.assertIn("MeshStager shutdown initiated", joined)
                self.assertIn("MeshStager shutdown complete", joined)
            finally:
                window.close()

    def test_on_thumb_refresh_batch_noops_after_shutdown(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                window._view_records = [_rec(Path(td) / "a.png")]
                window._shutdown_app(reason="test")
                window._on_thumb_refresh_batch(frozenset({_norm_path_key(Path(td) / "a.png")}))
            finally:
                window.close()

    def test_shutdown_app_is_idempotent(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                counter = {"n": 0}
                window._thumb_controller.request_shutdown = (  # type: ignore[assignment]
                    lambda *, timeout_ms=1500: counter.__setitem__("n", counter["n"] + 1)
                )
                window._shutdown_app(reason="first")
                window._shutdown_app(reason="second")
                self.assertEqual(counter["n"], 1)
            finally:
                window.close()

    def test_schedule_viewport_thumb_pass_noops_after_shutdown(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                window._view_records = [_rec(Path(td) / "a.png")]
                window._shutdown_app(reason="test")
                start_calls: list[int] = []
                window._viewport_thumb_timer.start = lambda *_a, **_kw: start_calls.append(1)  # type: ignore[method-assign]
                window._schedule_viewport_thumb_pass()
                self.assertEqual(start_calls, [])
            finally:
                window.close()

    def test_run_scan_noops_after_shutdown(self) -> None:
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            window = self._make_window()
            try:
                window._shutdown_app(reason="test")
                window._run_scan(td)
                self.assertIsNone(window._scan_thread)
            finally:
                window.close()

    def test_schedule_auto_thumbnails_noop_after_shutdown(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._shutdown_app(reason="test")
                # Should not raise and should not schedule anything.
                window._schedule_auto_thumbnails_after_scan()
                window._run_auto_thumbnails_after_scan()
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
