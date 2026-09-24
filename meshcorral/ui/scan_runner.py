"""Background folder scan runner (Qt worker thread).

Streams :func:`~meshcorral.services.scanner.iter_scan_file_records` off the GUI thread,
emitting ``batch_ready`` slices and throttled folder progress during the filesystem walk.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from meshcorral.models.file_record import FileRecord
from meshcorral.services.scan_cache_diagnostics import ScanCacheContext
from meshcorral.services.scan_cancel import ScanCancelToken
from meshcorral.services.scanner import iter_scan_file_records
from meshcorral.ui.scan_timing_profiler import ScanTimingSession
from meshcorral.utils.validators import require_existing_directory

log = logging.getLogger(__name__)

# Rows per Signal emit; balances UI churn vs responsiveness.
SCAN_UI_BATCH_SIZE: int = 200
# Yield between emits so the event loop can process paint/input (seconds).
_SCAN_BATCH_PAUSE_S: float = 0.005
# Minimum spacing between scan_progress Signals (directories can be very dense).
_PROGRESS_HEARTBEAT_S: float = 0.12


def _folder_label_for_progress(scan_root: Path, dir_base: Path) -> str:
    """Short relative path for status text (best-effort on resolve/relative failures)."""

    try:
        root_r = scan_root.resolve()
        base_r = dir_base.resolve()
    except OSError:
        return scan_root.name
    if base_r == root_r:
        return scan_root.name
    try:
        rel = dir_base.relative_to(scan_root)
        s = rel.as_posix()
        return s if s not in ("", ".") else scan_root.name
    except ValueError:
        return dir_base.name


class FolderScanRunner(QObject):
    """Walks folders on a worker thread and forwards batches to the GUI thread."""

    catalog_ready: Signal = Signal(object)
    catalog_reconciled: Signal = Signal(object)

    batch_ready: Signal = Signal(object)
    """Emitted with ``list[FileRecord]`` for each slice (≤ :data:`SCAN_UI_BATCH_SIZE`)."""

    scan_progress: Signal = Signal(int, str)
    """Emitted with *(matched_files_count, folder_hint)* during traversal (throttled)."""

    scan_failed: Signal = Signal(str)
    """Emitted with a human-readable error when scanning cannot complete."""

    scan_finished: Signal = Signal(float, int)
    """Emitted with *(elapsed_seconds, total_record_count)* after all batches."""

    scan_canceled: Signal = Signal(float, int)
    """Emitted with *(elapsed_seconds, partial_record_count)* when cooperatively stopped."""

    @Slot()
    def run_requested_scan(self) -> None:
        """QObject-bound entry point: Qt dispatches this on the worker thread."""
        self.execute_scan(*self.scan_request)

    @Slot(str, bool, object, bool, object, object, object)
    def execute_scan(
        self,
        folder: str,
        recursive: bool,
        allowed_extensions: object,
        lightweight: bool = False,
        cache_context: object = None,
        cancel_token: object = None,
        scan_timing: object = None,
    ) -> None:
        """Run filesystem scan until completion, failure, or cooperative cancel.

        When *lightweight* is True the worker skips ``Path.stat()`` and emits
        records with ``size_bytes`` / ``modified_time`` as ``None`` unless a
        v0.8 *cache_context* hydrates them from SQLite.

        *cancel_token* is a :class:`~meshcorral.services.scan_cancel.ScanCancelToken`
        polled at safe checkpoints; when set, the worker emits ``scan_canceled``.
        """

        scan_root = Path(folder)
        t0 = time.perf_counter()
        last_progress_emit_s = t0

        batch: list[FileRecord] = []
        matched_total = 0

        token = cancel_token if isinstance(cancel_token, ScanCancelToken) else None
        timing = scan_timing if isinstance(scan_timing, ScanTimingSession) else None
        if timing is not None:
            timing.log_started()

        def canceled() -> bool:
            return token is not None and token.is_canceled()

        def finish_timing(state: str, *, error: str = "") -> None:
            if timing is not None:
                timing.finish(state, error=error)

        def emit_canceled() -> None:
            finish_timing("canceled")
            self._safe_emit_canceled(time.perf_counter() - t0, matched_total)

        ctx = cache_context if isinstance(cache_context, ScanCacheContext) else None
        cache = ctx.metadata_cache if ctx else None
        catalog = None
        verified: list[FileRecord] = []
        if canceled():
            emit_canceled()
            return
        if cache is not None:
            try:
                catalog = cache.get_records_for_source_root(folder, recursive, allowed_extensions)
            except Exception:
                log.warning("Source catalog unavailable; using normal scan", exc_info=False)
        if catalog is not None:
            try:
                self.catalog_ready.emit(catalog)
            except RuntimeError:
                return
            ready = ctx.thumbnail_ready_cache
            if ready is not None:
                for source, thumbnail in catalog.thumbnail_hints:
                    if canceled():
                        emit_canceled()
                        return
                    ready.mark_ready(Path(source), Path(thumbnail))
        old_records = {str(rec.path): rec for rec in catalog.records} if catalog else {}

        try:
            require_existing_directory(scan_root, "Scan folder")
        except ValueError as exc:
            log.info("scan rejected: invalid folder: %s", exc)
            finish_timing("error", error=str(exc))
            self._safe_emit_failed(str(exc))
            return

        try:
            if canceled():
                emit_canceled()
                return
            if not self._safe_emit_progress(
                0, _folder_label_for_progress(scan_root, scan_root)
            ):
                return
            last_progress_emit_s = time.perf_counter()

            def on_dir_closed(count_so_far: int, dir_base: Path) -> None:
                """Forward walk position to Qt on a heartbeat so empty trees still animate."""

                nonlocal last_progress_emit_s
                if canceled():
                    return
                if timing is not None:
                    label = _folder_label_for_progress(scan_root, dir_base)
                    timing.note_discovery(count_so_far, label)
                    timing.log_heartbeat()
                now = time.perf_counter()
                if now - last_progress_emit_s < _PROGRESS_HEARTBEAT_S:
                    return
                last_progress_emit_s = now
                label = _folder_label_for_progress(scan_root, dir_base)
                self._safe_emit_progress(count_so_far, label)

            iterator = iter_scan_file_records(
                folder,
                recursive=recursive,
                allowed_extensions=allowed_extensions,  # type: ignore[arg-type]
                after_dir_scanned=on_dir_closed,
                lightweight=bool(lightweight) if catalog is None else False,
                metadata_cache=None,
                source_root=ctx.source_root if ctx else "",
                network_optimistic=bool(ctx.network_optimistic) if ctx else False,
                archive_manifest_cache=ctx.archive_manifest_cache if ctx else None,
                scan_cache_diagnostics=ctx.scan_cache_diagnostics if ctx else None,
                cancel_token=token,
                scan_timing=timing,
                strict_errors=cache is not None,
            )

            for rec in iterator:
                if canceled():
                    if batch:
                        self._safe_emit_batch(batch)
                    emit_canceled()
                    return
                matched_total += 1
                previous = old_records.get(str(rec.path))
                if previous is not None and (previous.size_bytes, previous.modified_time) == (rec.size_bytes, rec.modified_time):
                    rec = previous
                verified.append(rec)
                if catalog is not None:
                    continue
                batch.append(rec)
                if len(batch) >= SCAN_UI_BATCH_SIZE:
                    if not self._safe_emit_batch(batch):
                        return
                    batch = []
                    if canceled():
                        emit_canceled()
                        return
                    time.sleep(_SCAN_BATCH_PAUSE_S)

            if canceled():
                if batch:
                    self._safe_emit_batch(batch)
                emit_canceled()
                return

            if batch and not self._safe_emit_batch(batch):
                return
            if cache is not None:
                if not cache.complete_source_snapshot(folder, recursive, allowed_extensions, verified, canceled=canceled):
                    emit_canceled()
                    return
            if catalog is not None:
                self.catalog_reconciled.emit(verified)

        except Exception as exc:  # noqa: BLE001 — surface any scan failure to UI
            log.exception("streaming scan failed")
            if timing is not None:
                timing.finish("error", error=str(exc))
            self._safe_emit_failed(str(exc))
            return

        if canceled():
            emit_canceled()
            return

        elapsed = time.perf_counter() - t0
        finish_timing("complete")
        self._safe_emit_finished(elapsed, matched_total)

    def _safe_emit_progress(self, count: int, label: str) -> bool:
        """Emit ``scan_progress`` defensively. False = signal source destroyed."""
        try:
            self.scan_progress.emit(count, label)
            return True
        except RuntimeError:
            log.debug("scan_progress emit aborted: signal source deleted")
            return False

    def _safe_emit_batch(self, batch: list[FileRecord]) -> bool:
        """Emit ``batch_ready`` defensively. False = signal source destroyed."""
        try:
            self.batch_ready.emit(batch)
            return True
        except RuntimeError:
            log.debug("batch_ready emit aborted: signal source deleted")
            return False

    def _safe_emit_failed(self, message: str) -> None:
        """Emit ``scan_failed`` defensively (never raises)."""
        try:
            self.scan_failed.emit(message)
        except RuntimeError:
            log.debug("scan_failed emit aborted: signal source deleted")

    def _safe_emit_finished(self, elapsed: float, total: int) -> None:
        """Emit ``scan_finished`` defensively (never raises)."""
        try:
            self.scan_finished.emit(elapsed, total)
        except RuntimeError:
            log.debug("scan_finished emit aborted: signal source deleted")

    def _safe_emit_canceled(self, elapsed: float, total: int) -> None:
        """Emit ``scan_canceled`` defensively (never raises)."""
        try:
            self.scan_canceled.emit(elapsed, total)
        except RuntimeError:
            log.debug("scan_canceled emit aborted: signal source deleted")
