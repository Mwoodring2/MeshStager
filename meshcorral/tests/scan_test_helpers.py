"""Shared stubs for MainWindow scan-launch tests (async large-folder preflight)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable
from unittest import mock

from PySide6.QtCore import QTimer

if TYPE_CHECKING:
    from meshcorral.ui.main_window import MainWindow


def _run_timer_callback_immediately(_ms: int, fn: object) -> None:
    """Invoke a ``QTimer.singleShot`` callback synchronously (test helper)."""
    if callable(fn):
        fn()


def stub_immediate_scan_launch(
    window: "MainWindow",
    run_scan_calls: list[str],
) -> None:
    """
    Bypass large-folder dialog and deferred QTimer so tests hit ``_run_scan`` immediately.

    Patches ``_confirm_large_folder_scan`` and ``_deferred_run_scan_if_launched`` on *window*.
    """

    def _confirm(
        source_path: str,
        *,
        timer: object | None = None,
        on_done: Callable[[bool], None] | None = None,
    ) -> bool | None:
        _ = source_path, timer
        if on_done is not None:
            with mock.patch.object(QTimer, "singleShot", _run_timer_callback_immediately):
                on_done(True)
        return None

    def _deferred(source_path: str, launch_gen: int, timer: object) -> None:
        _ = launch_gen, timer
        window._run_scan(source_path)  # type: ignore[misc]

    window._confirm_large_folder_scan = _confirm  # type: ignore[method-assign]
    window._deferred_run_scan_if_launched = _deferred  # type: ignore[method-assign]
