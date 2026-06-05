"""
Background queue for Blender Bridge jobs: one worker thread, FIFO order, non-blocking UI.

Cancels only apply to items still in the in-memory queue (files under ``pending/``), not
the job currently being executed in Blender.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from meshcorral.app.bridge import job_runner
from meshcorral.app.bridge.blender_locator import find_blender_executable
from meshcorral.app.bridge.bridge_backpressure import (
    MAX_PENDING_BRIDGE_JOBS_LOCAL,
    BridgeEnqueueReject,
    bridge_load_count,
    max_pending_bridge_jobs,
)
from meshcorral.app.bridge.job_origin import JobOrigin
from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.thumbnail_routing_policy import (
    ThumbnailManualOverride,
    route_thumbnail,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QueuedJobInfo:
    """One row in the pending-queue UI."""

    job_id: str
    source_filename: str
    source_path: Path | None
    job_type: str
    job_path: Path


def _filename_from_path(p: str | Path) -> str:
    return Path(p).name


class BridgeQueueManager(QObject):
    """
    Add thumbnail jobs on the main thread; a daemon worker runs them one at a time.

    Emits ``queue_count_changed`` and ``job_completed`` from the worker thread; Qt
    uses queued connections, so UI slots stay on the main thread.
    """

    queue_count_changed = Signal(int)
    running_job_id_changed = Signal(object)  # str | None
    running_source_path_changed = Signal(object)  # Path | None
    job_completed = Signal(object)  # BridgeJobResult

    def __init__(self, settings: SettingsService, parent: QObject | None = None) -> None:
        """
        Wire the bridge queue manager to *settings* and start the background worker.

        The worker runs forever as a daemon thread; call :meth:`shutdown` from the UI
        thread on application exit.
        """
        super().__init__(parent)
        self._settings = settings
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._items: list[tuple[Path, Path]] = []  # job_json_path, blender_exe
        # Maps job_id -> JobOrigin. Populated on enqueue, cleared on completion.
        # Lets the UI gate severity-aware UX (modal vs footer) without changing the
        # on-disk result.json schema or reaching across the worker thread boundary.
        self._job_origins: dict[str, JobOrigin] = {}
        self._in_flight_source_keys: set[str] = set()
        self._max_pending_cap: int = MAX_PENDING_BRIDGE_JOBS_LOCAL
        self._worker_stop = False
        self._enqueue_closed = False
        self._worker_busy = False
        self._ui_quiet = False
        self._thread = threading.Thread(
            target=self._worker_main,
            name="BridgeBlenderQueue",
            daemon=True,
        )
        self._thread.start()

    def set_ui_quiet(self, quiet: bool) -> None:
        """When True, per-job enqueue/finish logs use debug level (prime perf batches)."""
        self._ui_quiet = bool(quiet)

    def configure_backpressure(self, *, network_like: bool) -> None:
        """Set pending+running cap from Prime v0.10 local/remote limits."""
        self._max_pending_cap = max_pending_bridge_jobs(network_like=bool(network_like))

    def max_pending_cap(self) -> int:
        """Current pending+running cap (local or remote)."""
        return int(self._max_pending_cap)

    def in_flight_load(self) -> tuple[int, int]:
        """Return ``(pending_count, running_count)`` for diagnostics."""
        with self._lock:
            pending = len(self._items)
            running = 1 if self._worker_busy else 0
        return pending, running

    def bridge_load(self) -> int:
        """Pending plus running bridge jobs."""
        pending, running = self.in_flight_load()
        return bridge_load_count(pending=pending, running=running)

    def has_source_in_flight(self, source_path: Path) -> bool:
        """True when *source_path* already has a pending or running bridge job."""
        key = _norm_path_key(source_path)
        with self._lock:
            return key in self._in_flight_source_keys

    def _log_info(self, msg: str, *args: object) -> None:
        if self._ui_quiet:
            logger.debug(msg, *args)
        else:
            logger.info(msg, *args)

    def try_enqueue_thumbnail(
        self,
        source_path: Path,
        *,
        origin: JobOrigin = JobOrigin.MANUAL_SINGLE,
        manual_override: ThumbnailManualOverride = ThumbnailManualOverride.DEFAULT,
    ) -> tuple[bool, str, BridgeEnqueueReject]:
        """
        Enqueue a thumbnail job if Blender is available.

        Parameters
        ----------
        source_path:
            Read-only mesh file to thumbnail.
        origin:
            Severity tier for the request (see :class:`JobOrigin`). Used by the UI to
            decide whether a failure should raise a modal or remain a footer message.
            Defaults to :attr:`JobOrigin.MANUAL_SINGLE` for backwards compatibility
            with older callers; new callers should pass an explicit value.

        Returns
        -------
        tuple[bool, str, BridgeEnqueueReject]
            ``(True, "", OK)`` on success, or ``(False, message, reason)`` when
            Blender is unavailable, the queue is at cap, or the source is already
            pending/running.
        """
        source_key = _norm_path_key(source_path)
        route_plan = route_thumbnail(
            Path(source_path),
            self._settings,
            manual_override=manual_override,
        )
        if route_plan.backend == "native":
            return (
                False,
                "Native CPU renderer owns this format; Blender Bridge was not used.",
                BridgeEnqueueReject.NOT_ROUTED,
            )
        if route_plan.backend == "none":
            return False, route_plan.reason, BridgeEnqueueReject.NOT_ROUTED
        with self._lock:
            if self._enqueue_closed:
                return False, "Application is shutting down.", BridgeEnqueueReject.SHUTDOWN
            if source_key in self._in_flight_source_keys:
                return (
                    False,
                    "Thumbnail job already queued for this file.",
                    BridgeEnqueueReject.DUPLICATE,
                )
            pending = len(self._items)
            running = 1 if self._worker_busy else 0
            if bridge_load_count(pending=pending, running=running) >= self._max_pending_cap:
                return (
                    False,
                    "Bridge thumbnail queue is full; try again shortly.",
                    BridgeEnqueueReject.CAP,
                )
        b = find_blender_executable(self._settings)
        if b is None:
            return (
                False,
                "Blender was not found. Set the full path to blender.exe in Settings → "
                "Blender Bridge, or install Blender, then try again.",
                BridgeEnqueueReject.NO_BLENDER,
            )
        try:
            job_path = job_runner.enqueue_generate_thumbnail_job(
                source_path,
                self._settings,
            )
        except OSError as e:
            return False, f"Could not create job file: {e}", BridgeEnqueueReject.IO_ERROR

        job_id = job_runner.job_id_from_job_filename(job_path)
        coerced_origin = JobOrigin.coerce(origin)
        with self._cond:
            self._items.append((job_path, b))
            self._job_origins[job_id] = coerced_origin
            self._in_flight_source_keys.add(source_key)
            n = len(self._items)
            self._cond.notify()
        self._log_info(
            "Bridge enqueue thumbnail job %s (origin=%s, source=%s)",
            job_id,
            coerced_origin.value,
            source_path,
        )
        self.queue_count_changed.emit(n)
        return True, "", BridgeEnqueueReject.OK

    def job_origin_for_job_id(self, job_id: str) -> JobOrigin | None:
        """
        Return the recorded :class:`JobOrigin` for *job_id*, or ``None`` if unknown.

        Unknown ids include jobs whose origin was already consumed (for example,
        completion has been processed) or jobs enqueued through other code paths
        (legacy tests, direct ``run_job_now`` calls). Callers should treat ``None`` as
        "background" — the safer, non-blocking default.

        This is a non-destructive read; use :meth:`pop_job_origin_for_job_id` from the
        completion handler to keep the in-memory map bounded.
        """
        with self._lock:
            return self._job_origins.get(str(job_id))

    def pop_job_origin_for_job_id(self, job_id: str) -> JobOrigin | None:
        """
        Read and remove the recorded :class:`JobOrigin` for *job_id*.

        Used by the completion handler to look up severity exactly once and avoid
        unbounded growth of the internal map across a long session.
        """
        with self._lock:
            return self._job_origins.pop(str(job_id), None)

    def _worker_main(self) -> None:
        while True:
            with self._cond:
                while not self._items and not self._worker_stop:
                    self._cond.wait(timeout=0.4)
                if self._worker_stop and not self._items:
                    break
                if not self._items:
                    continue
                job_path, blender = self._items.pop(0)
                remaining = len(self._items)
                self._worker_busy = True
            self.queue_count_changed.emit(remaining)
            jid = job_runner.job_id_from_job_filename(job_path)
            self.running_job_id_changed.emit(jid)
            # Best-effort: surface source path for UI "generating" state.
            src_path: Path | None = None
            try:
                if job_path.is_file():
                    data = json.loads(job_path.read_text(encoding="utf-8"))
                    sp = data.get("source_path")
                    if sp:
                        src_path = Path(str(sp))
            except (OSError, json.JSONDecodeError, UnicodeError, TypeError, ValueError):
                src_path = None
            self.running_source_path_changed.emit(src_path)
            completed_key: str | None = None
            if src_path is not None:
                completed_key = _norm_path_key(src_path)
            try:
                result = job_runner.run_job_now(
                    job_path,
                    self._settings,
                    blender_executable=blender,
                )
                self.job_completed.emit(result)
            finally:
                self.running_job_id_changed.emit(None)
                self.running_source_path_changed.emit(None)
                with self._lock:
                    self._worker_busy = False
                    if completed_key is not None:
                        self._in_flight_source_keys.discard(completed_key)
            try:
                self._log_info(
                    "Bridge queue job %s finished: %s",
                    result.job_id,
                    result.status.value,
                )
            except (AttributeError, ValueError) as e:
                logger.debug("log status: %s", e)

    def queue_length(self) -> int:
        """Return the number of jobs waiting to run (not the one currently running)."""
        with self._lock:
            return len(self._items)

    def pending_count(self) -> int:
        """Alias for :meth:`queue_length` (shutdown diagnostics)."""
        return self.queue_length()

    def pending_jobs(self) -> list[QueuedJobInfo]:
        """
        Return ordered snapshot of queued jobs (main thread, for UI only).

        Jobs still on disk in ``pending/``; skipped if a row cannot be read.
        """
        with self._lock:
            snapshot = list(self._items)
        out: list[QueuedJobInfo] = []
        for job_path, _ in snapshot:
            if not job_path.is_file():
                continue
            try:
                data = json.loads(job_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError) as e:
                logger.debug("Skip bad queue line %s: %s", job_path, e)
                continue
            job_id = str(data.get("job_id", job_runner.job_id_from_job_filename(job_path)))
            jt = str(data.get("job_type", "unknown"))
            src = str(data.get("source_path", ""))
            name = _filename_from_path(src) if src else "—"
            src_path = Path(src) if src else None
            out.append(
                QueuedJobInfo(
                    job_id=job_id,
                    source_filename=name,
                    source_path=src_path,
                    job_type=jt,
                    job_path=job_path,
                )
            )
        return out

    def cancel_queued_job_id(self, job_id: str) -> bool:
        """
        Remove a single queued job (must not be the currently running job).

        Returns True if a matching item was found and the pending file was cancelled.
        """
        to_cancel: Path | None = None
        cancelled_id: str | None = None
        with self._cond:
            for i, (p, _) in enumerate(self._items):
                pid = job_runner.job_id_from_job_filename(p)
                if pid == job_id or p.name == f"{job_id}.job.json":
                    to_cancel = self._items.pop(i)[0]
                    cancelled_id = pid
                    break
            if cancelled_id is not None:
                self._job_origins.pop(cancelled_id, None)
            n = len(self._items)
        if to_cancel is None:
            return False
        self._drop_in_flight_key_for_job_path(to_cancel)
        job_runner.cancel_pending_job_file(to_cancel)
        self.queue_count_changed.emit(n)
        return True

    def cancel_all_queued(self) -> int:
        """Remove every item still in the internal queue. Returns the number of attempts."""
        to_cancel: list[Path] = []
        with self._cond:
            while self._items:
                p, _ = self._items.pop(0)
                to_cancel.append(p)
                self._job_origins.pop(job_runner.job_id_from_job_filename(p), None)
            n = len(self._items)
        count = 0
        for p in to_cancel:
            self._drop_in_flight_key_for_job_path(p)
            if job_runner.cancel_pending_job_file(p):
                count += 1
        self.queue_count_changed.emit(n)
        return count

    def is_shutting_down(self) -> bool:
        """True once enqueue has been closed (application shutdown)."""
        with self._lock:
            return bool(self._enqueue_closed)

    def request_stop(self) -> None:
        """Stop accepting new jobs and wake the worker so it can exit."""
        with self._cond:
            self._enqueue_closed = True
            self._worker_stop = True
            self._cond.notify_all()

    def cancel_pending(self) -> int:
        """Cancel every job still in the in-memory queue (not the active Blender run)."""
        return self.cancel_all_queued()

    def active_count(self) -> int:
        """Return 1 when a Blender job is actively running, else 0."""
        with self._lock:
            return 1 if self._worker_busy else 0

    def _drop_in_flight_key_for_job_path(self, job_path: Path) -> None:
        """Remove a source key from the in-flight set when a pending job is cancelled."""
        try:
            if not job_path.is_file():
                return
            data = json.loads(job_path.read_text(encoding="utf-8"))
            sp = data.get("source_path")
            if not sp:
                return
            key = _norm_path_key(Path(str(sp)))
        except (OSError, json.JSONDecodeError, UnicodeError, TypeError, ValueError):
            return
        with self._lock:
            self._in_flight_source_keys.discard(key)

    def shutdown(
        self,
        timeout: float = 1.0,
        *,
        active_job_wait_s: float = 3.0,
        close_enqueue: bool = True,
    ) -> None:
        """
        Cancel pending jobs, request worker stop, and join with bounded waits.

        Does not forcibly kill an in-progress Blender subprocess; waits up to
        *active_job_wait_s* for the current job to finish, then joins the worker
        thread for *timeout* seconds. Re-entry-safe.

        When *close_enqueue* is False (unit tests), the worker stops but
        :meth:`try_enqueue_thumbnail` may still queue items in memory.
        """
        with self._cond:
            already = self._worker_stop
            self._worker_stop = True
            if close_enqueue:
                self._enqueue_closed = True
            self._cond.notify_all()
        if not already and close_enqueue:
            self.cancel_pending()
        deadline = time.monotonic() + max(0.0, float(active_job_wait_s))
        while time.monotonic() < deadline:
            with self._lock:
                busy = self._worker_busy
            if not busy:
                break
            time.sleep(0.05)
        else:
            with self._lock:
                still_busy = self._worker_busy
            if still_busy:
                logger.warning(
                    "Bridge queue: active Blender job still running after %.1fs; "
                    "continuing shutdown",
                    active_job_wait_s,
                )
        if already and not self._thread.is_alive():
            return
        self._thread.join(timeout=max(0.0, float(timeout)))
        if self._thread.is_alive():
            logger.info(
                "Bridge queue worker did not stop within %.1fs; leaving as daemon",
                timeout,
            )
