"""Tests for async teardown races between pool workers and their QObject owners.

Two failure modes are pinned here:

* A ``QRunnable`` finishing after its owning ``QObject`` was destroyed used to raise
  ``RuntimeError: Signal source has been deleted`` from ``emit()`` on a pool thread,
  where nothing can catch it. Deleted signal targets must be treated as ordinary
  cancellation instead.
* A ``QThread`` owned by ``MainWindow`` must be asked to stop and must have finished
  before Qt destroys the window, otherwise Qt logs
  ``QThread: Destroyed while thread is still running``.
"""

from __future__ import annotations

import sys
import unittest
import uuid

import shiboken6
from PySide6.QtCore import QCoreApplication, QObject, QSettings, QThread
from PySide6.QtWidgets import QApplication

from meshcorral.utils.qt_object_safety import emit_if_alive, is_qobject_alive


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication(sys.argv)
    return inst  # type: ignore[return-value]


class _SettingsSandbox:
    """Isolate QSettings writes so window tests do not touch the real profile."""

    def __init__(self) -> None:
        self._org = QCoreApplication.organizationName() or ""
        self._app = QCoreApplication.applicationName() or ""
        self._test_id = f"meshcorral-tests-{uuid.uuid4().hex[:8]}"

    def __enter__(self) -> "_SettingsSandbox":
        QCoreApplication.setOrganizationName("MeshCorralTests")
        QCoreApplication.setApplicationName(self._test_id)
        QSettings().clear()
        return self

    def __exit__(self, *exc: object) -> None:
        QSettings().clear()
        QCoreApplication.setOrganizationName(self._org)
        QCoreApplication.setApplicationName(self._app)


class TestQObjectSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_live_object_reports_alive(self) -> None:
        obj = QObject()
        self.assertTrue(is_qobject_alive(obj))

    def test_destroyed_object_reports_dead(self) -> None:
        obj = QObject()
        shiboken6.delete(obj)
        self.assertFalse(is_qobject_alive(obj))

    def test_none_reports_dead(self) -> None:
        self.assertFalse(is_qobject_alive(None))

    def test_emit_if_alive_delivers_to_live_target(self) -> None:
        from meshcorral.ui.thumbnail_controller import _RasterReadySignals

        sigs = _RasterReadySignals()
        seen: list[object] = []
        sigs.paths_ready.connect(seen.append)

        self.assertTrue(emit_if_alive(sigs, "paths_ready", ["a"]))
        self.assertEqual(seen, [["a"]])

    def test_emit_if_alive_returns_false_for_destroyed_target(self) -> None:
        from meshcorral.ui.thumbnail_controller import _RasterReadySignals

        sigs = _RasterReadySignals()
        shiboken6.delete(sigs)

        self.assertFalse(emit_if_alive(sigs, "paths_ready", ["a"]))

    def test_emit_if_alive_returns_false_for_unknown_signal(self) -> None:
        self.assertFalse(emit_if_alive(QObject(), "not_a_signal", 1))


class TestThumbnailRunnableTeardown(unittest.TestCase):
    """``run()`` on a runnable whose controller is gone must return, not raise."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_load_runnable_with_destroyed_signals_does_not_raise(self) -> None:
        from meshcorral.ui.thumbnail_controller import _ImageLoadSignals, _LoadRunnable

        sigs = _ImageLoadSignals()
        runnable = _LoadRunnable(
            purpose="gallery",
            key="k",
            abs_thumb="does-not-exist.png",
            px=96,
            sigs=sigs,
        )
        shiboken6.delete(sigs)

        runnable.run()  # MUST NOT raise

    def test_load_runnable_stale_path_with_destroyed_signals_does_not_raise(self) -> None:
        from meshcorral.ui.thumbnail_controller import _ImageLoadSignals, _LoadRunnable

        sigs = _ImageLoadSignals()
        runnable = _LoadRunnable(
            purpose="table",
            key="k",
            abs_thumb="does-not-exist.png",
            px=96,
            sigs=sigs,
            epoch=1,
            current_epoch_fn=lambda: 9,
        )
        shiboken6.delete(sigs)

        runnable.run()  # MUST NOT raise

    def test_raster_ready_runnable_with_destroyed_signals_does_not_raise(self) -> None:
        from meshcorral.ui.thumbnail_controller import (
            _RasterReadyRunnable,
            _RasterReadySignals,
        )

        sigs = _RasterReadySignals()
        runnable = _RasterReadyRunnable([], sigs)
        shiboken6.delete(sigs)

        runnable.run()  # MUST NOT raise

    def test_native_runnable_with_destroyed_manager_does_not_raise(self) -> None:
        from meshcorral.services.thumbnails.native_thumbnail_queue import (
            NativeThumbnailQueueManager,
            _NativeThumbRunnable,
        )
        from meshcorral.services.settings_service import SettingsService
        from meshcorral.services.thumbnails.thumbnail_router import ThumbnailRouter
        from pathlib import Path

        manager = NativeThumbnailQueueManager(ThumbnailRouter(SettingsService()))
        runnable = _NativeThumbRunnable(
            manager,
            Path("does-not-exist.stl"),
            "job-1",
            max_px=128,
            fallback_on_fail=False,
            for_auto_enqueue=False,
            high_quality=False,
        )
        shiboken6.delete(manager)

        runnable.run()  # MUST NOT raise


class TestMainWindowThreadOwnership(unittest.TestCase):
    """Owned ``QThread`` objects must be stopped and joined before the owner dies."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_geometry_thread_is_not_started_until_needed(self) -> None:
        """A freshly built window owns no running thread that could outlive it."""
        with _SettingsSandbox():
            window = self._make_window()
            try:
                thread = window._geometry_meta_thread
                self.assertIsNotNone(thread)
                if thread is not None:
                    self.assertFalse(thread.isRunning())
            finally:
                window.close()

    def test_lazy_start_then_shutdown_leaves_no_running_thread(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                self.assertTrue(window._ensure_geometry_metadata_thread())
                thread = window._geometry_meta_thread
                self.assertIsNotNone(thread)
                if thread is not None:
                    self.assertTrue(thread.isRunning())
                    window._shutdown_app(reason="test")
                    self.assertFalse(thread.isRunning())
                    self.assertIsNone(window._geometry_meta_thread)
            finally:
                window.close()

    def test_shutdown_waits_for_enrichment_thread(self) -> None:
        """Shutdown must join the enrichment thread; interactive cancel must not."""
        with _SettingsSandbox():
            window = self._make_window()
            try:
                thread = QThread(window)
                thread.start()
                window._enrichment_thread = thread
                window._enrichment_in_progress = True

                window._cancel_active_enrichment(wait_ms=2_000)

                self.assertFalse(thread.isRunning())
                self.assertIsNone(window._enrichment_thread)
            finally:
                window.close()

    def test_interactive_cancel_does_not_block(self) -> None:
        """Starting a new scan must not join the worker on the UI thread."""
        with _SettingsSandbox():
            window = self._make_window()
            thread = QThread(window)
            thread.start()
            try:
                window._enrichment_thread = thread
                window._enrichment_in_progress = True

                window._cancel_active_enrichment()

                self.assertIsNone(window._enrichment_thread)
                self.assertFalse(window._enrichment_in_progress)
            finally:
                thread.quit()
                thread.wait(2_000)
                window.close()

    def test_shutdown_is_idempotent(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            try:
                window._shutdown_app(reason="test-first")
                window._shutdown_app(reason="test-second")  # MUST NOT raise
            finally:
                window.close()

    def test_no_owned_thread_running_after_close(self) -> None:
        with _SettingsSandbox():
            window = self._make_window()
            window._ensure_geometry_metadata_thread()
            window.close()

            for attr in ("_geometry_meta_thread", "_enrichment_thread", "_scan_thread"):
                thread = getattr(window, attr, None)
                if isinstance(thread, QThread):
                    self.assertFalse(thread.isRunning(), f"{attr} still running after close")


if __name__ == "__main__":
    unittest.main()
