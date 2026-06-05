"""Tests for the metadata enrichment lifecycle / dead-thread defenses.

Regression captured from a real session:

* User clicks Scan Source after a prior scan's enrichment thread has already
  finished — Qt's ``deleteLater`` chain destroyed the C++ ``QThread``, but
  ``self._enrichment_thread`` still pointed at the dead Python proxy. The
  follow-up ``_cancel_active_enrichment`` then called ``thr.isRunning()`` and
  raised ``RuntimeError: libshiboken: Internal C++ object already deleted``.
* The same crash recurred inside ``closeEvent`` via
  ``_shutdown_app -> _cancel_active_enrichment``.

After the fix:

* ``_on_enrichment_thread_finished`` nulls both handles when the thread
  finishes, before ``deleteLater`` destroys the C++ side.
* ``_cancel_active_enrichment`` is defensive against ``RuntimeError`` from
  shiboken when the proxies happen to be stale anyway.
"""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst  # type: ignore[return-value]


class _DeadThreadProxy:
    """Mimic a shiboken-destroyed ``QThread``: every accessor raises ``RuntimeError``."""

    def isRunning(self) -> bool:  # noqa: N802 - Qt API name
        raise RuntimeError("Internal C++ object (QThread) already deleted.")

    def quit(self) -> None:
        raise RuntimeError("Internal C++ object (QThread) already deleted.")

    def wait(self, _ms: int) -> bool:  # noqa: D401
        raise RuntimeError("Internal C++ object (QThread) already deleted.")


class _DeadRunnerProxy:
    """Mimic a shiboken-destroyed enrichment runner: ``cancel()`` raises."""

    def cancel(self) -> None:
        raise RuntimeError("Internal C++ object already deleted.")


class TestEnrichmentLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def _make_window(self):  # type: ignore[no-untyped-def]
        from meshcorral.ui.main_window import MainWindow

        return MainWindow()

    def test_cancel_active_enrichment_survives_dead_qthread(self) -> None:
        window = self._make_window()
        try:
            window._enrichment_thread = _DeadThreadProxy()  # type: ignore[assignment]
            window._enrichment_runner = _DeadRunnerProxy()  # type: ignore[assignment]
            window._enrichment_in_progress = True

            # MUST NOT raise — the user-visible regression was an uncaught
            # RuntimeError from shiboken bubbling out of _cancel_active_enrichment.
            window._cancel_active_enrichment()

            self.assertIsNone(window._enrichment_thread)
            self.assertIsNone(window._enrichment_runner)
            self.assertFalse(window._enrichment_in_progress)
        finally:
            window.close()

    def test_enrichment_thread_finished_handler_clears_handles(self) -> None:
        """The ``QThread.finished`` slot must null handles before C++ deletion."""
        window = self._make_window()
        try:
            sentinel_thr = _DeadThreadProxy()
            window._enrichment_thread = sentinel_thr  # type: ignore[assignment]
            window._enrichment_runner = _DeadRunnerProxy()  # type: ignore[assignment]
            window._enrichment_in_progress = True

            # No sender(): the slot's identity guard sees ``None`` and proceeds.
            window._on_enrichment_thread_finished()

            self.assertIsNone(window._enrichment_thread)
            self.assertIsNone(window._enrichment_runner)
            self.assertFalse(window._enrichment_in_progress)
        finally:
            window.close()

    def test_close_event_does_not_raise_when_enrichment_proxy_is_dead(self) -> None:
        """``closeEvent → _shutdown_app → _cancel_active_enrichment`` must not raise."""
        window = self._make_window()
        try:
            window._enrichment_thread = _DeadThreadProxy()  # type: ignore[assignment]
            window._enrichment_runner = _DeadRunnerProxy()  # type: ignore[assignment]
            window._enrichment_in_progress = True

            # Should complete the shutdown sequence cleanly.
            window._shutdown_app(reason="test")

            self.assertTrue(window._shutting_down)
            self.assertIsNone(window._enrichment_thread)
            self.assertIsNone(window._enrichment_runner)
        finally:
            # window already shut down; close() is a no-op but safe.
            window.close()


if __name__ == "__main__":
    unittest.main()
