"""Tests for worker-signal teardown safety.

Regression captured from a real session (exit code ``0xC0000409``,
``STATUS_STACK_BUFFER_OVERRUN``):

* ``_on_scan_thread_finished_cleanup`` had no sender-identity guard. A queued
  ``QThread.finished`` from a *previous* scan could fire after a new scan had
  already registered new ``self._scan_runner`` / ``self._scan_thread``
  references, nulling them. Python GC then destroyed the new runner C++ side
  mid-``execute_scan``, raising ``RuntimeError: Signal source has been
  deleted`` from inside ``scan_progress.emit`` — which the worker couldn't
  recover from, cascading into a Windows fast-fail exit.

* Both worker runners (``MetadataEnrichmentRunner`` and
  ``FolderScanRunner``) needed defensive ``try / except RuntimeError`` around
  every signal emit so a destroyed C++ proxy mid-pump degrades to a clean
  return rather than propagating into a stack overrun.
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication, QObject, QSettings, QThread, Signal
from PySide6.QtWidgets import QApplication


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


class _StaleThreadSender(QObject):
    """Stand-in for an old ``QThread`` that emits ``finished``-shaped sender."""

    finished: Signal = Signal()


class TestScanCleanupSenderGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_stale_finished_does_not_clobber_new_scan_handles(self) -> None:
        """A ``finished`` from an older scan thread must not null new handles."""
        with _SettingsSandbox():
            window = self._make_window()
            try:
                # Pretend a new scan is in flight with a real new thread + runner.
                new_thread = QThread()
                new_runner = QObject()
                window._scan_thread = new_thread
                window._scan_runner = new_runner

                # Simulate the OLD thread's finished slot firing now. We make
                # sender() return something other than new_thread by invoking
                # the slot via signal->slot from a stale emitter.
                stale = _StaleThreadSender()
                stale.finished.connect(window._on_scan_thread_finished_cleanup)
                stale.finished.emit()
                QApplication.processEvents()

                # Guard must have rejected the stale sender; new handles intact.
                self.assertIs(window._scan_thread, new_thread)
                self.assertIs(window._scan_runner, new_runner)
            finally:
                # Manual cleanup to keep test environment tidy.
                if not new_thread.isRunning():
                    new_thread.deleteLater()
                window._scan_thread = None
                window._scan_runner = None
                window.close()

    def test_direct_call_with_no_sender_still_cleans_up(self) -> None:
        """``_on_scan_thread_finished_cleanup`` called directly must clean handles."""
        with _SettingsSandbox():
            window = self._make_window()
            try:
                thr = QThread()
                runner = QObject()
                window._scan_thread = thr
                window._scan_runner = runner

                # No QObject signal => sender() returns None => guard passes.
                window._on_scan_thread_finished_cleanup()

                self.assertIsNone(window._scan_thread)
                self.assertIsNone(window._scan_runner)
            finally:
                window.close()


class _RaisingSignal:
    """Stand-in for a bound PySide ``SignalInstance`` whose C++ side is gone."""

    def __init__(self, message: str = "Signal source has been deleted") -> None:
        self._message = message
        self.emit_call_count = 0

    def emit(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        self.emit_call_count += 1
        raise RuntimeError(self._message)


class TestEnrichmentRunnerEmitSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_finished_emit_swallows_signal_source_deleted(self) -> None:
        """``_safe_emit_finished`` must not propagate shiboken RuntimeError."""
        from meshcorral.ui.metadata_enrichment_runner import MetadataEnrichmentRunner

        runner = MetadataEnrichmentRunner()
        raising = _RaisingSignal()
        # Shadow the bound signal on the instance dict.
        runner.enrichment_finished = raising  # type: ignore[assignment]

        # MUST NOT raise.
        runner._safe_emit_finished(7)
        self.assertEqual(raising.emit_call_count, 1)

    def test_batch_emit_returns_false_on_signal_source_deleted(self) -> None:
        from meshcorral.ui.metadata_enrichment_runner import MetadataEnrichmentRunner

        runner = MetadataEnrichmentRunner()
        runner.batch_ready = _RaisingSignal()  # type: ignore[assignment]

        self.assertFalse(runner._safe_emit_batch([]))

    def test_execute_enrichment_handles_destroyed_self_mid_loop(self) -> None:
        """If a batch emit fails mid-pump, the runner stops cleanly."""
        from meshcorral.ui.metadata_enrichment_runner import MetadataEnrichmentRunner

        runner = MetadataEnrichmentRunner()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.txt"
            p.write_text("x")
            with mock.patch.object(
                runner, "_safe_emit_batch", return_value=False
            ) as patched:
                # MUST NOT raise even though batch emit "fails".
                runner.execute_enrichment([(str(p), p)], 1, 0.0)
                self.assertTrue(patched.called)


class TestScanRunnerEmitSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_progress_emit_handles_deleted_signal_source(self) -> None:
        from meshcorral.ui.scan_runner import FolderScanRunner

        runner = FolderScanRunner()
        runner.scan_progress = _RaisingSignal()  # type: ignore[assignment]

        self.assertFalse(runner._safe_emit_progress(0, "label"))

    def test_failed_emit_never_raises(self) -> None:
        from meshcorral.ui.scan_runner import FolderScanRunner

        runner = FolderScanRunner()
        runner.scan_failed = _RaisingSignal()  # type: ignore[assignment]

        # MUST NOT raise (previously cascaded into the 0xC0000409 crash).
        runner._safe_emit_failed("boom")

    def test_finished_emit_never_raises(self) -> None:
        from meshcorral.ui.scan_runner import FolderScanRunner

        runner = FolderScanRunner()
        runner.scan_finished = _RaisingSignal()  # type: ignore[assignment]

        runner._safe_emit_finished(0.1, 5)

    def test_canceled_emit_never_raises(self) -> None:
        from meshcorral.ui.scan_runner import FolderScanRunner

        runner = FolderScanRunner()
        runner.scan_canceled = _RaisingSignal()  # type: ignore[assignment]

        runner._safe_emit_canceled(0.1, 5)


if __name__ == "__main__":
    unittest.main()
