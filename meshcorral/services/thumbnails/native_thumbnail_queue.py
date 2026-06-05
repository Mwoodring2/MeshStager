"""
Background queue for CPU-native thumbnail generation (Prime v1.0 local optimization).

Runs native renders off the UI thread via :class:`QThreadPool` and emits
:class:`~meshcorral.app.bridge.job_models.BridgeJobResult` for index/UI integration.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.services.environment.native_renderer_health import get_native_renderer_health
from meshcorral.services.thumbnails.thumbnail_router import ThumbnailRouter

logger = logging.getLogger(__name__)

MAX_NATIVE_IN_FLIGHT: int = 8


class NativeEnqueueReject(str, Enum):
    """Reason a native enqueue attempt was rejected."""

    OK = ""
    DUPLICATE = "duplicate"
    CAP = "cap"
    SHUTDOWN = "shutdown"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class _NativeThumbRunnable(QRunnable):
    """Worker runnable: generate one native thumbnail."""

    def __init__(
        self,
        manager: "NativeThumbnailQueueManager",
        source_path: Path,
        job_id: str,
        *,
        max_px: int,
        fallback_on_fail: bool,
        for_auto_enqueue: bool,
        high_quality: bool,
    ) -> None:
        super().__init__()
        self._manager = manager
        self._source_path = Path(source_path)
        self._job_id = job_id
        self._max_px = int(max_px)
        self._fallback_on_fail = bool(fallback_on_fail)
        self._for_auto_enqueue = bool(for_auto_enqueue)
        self._high_quality = bool(high_quality)

    def run(self) -> None:
        result, geometry_summary = self._manager._router.generate_native_to_cache(
            self._source_path,
            job_id=self._job_id,
            max_px=self._max_px,
            fallback_on_fail=self._fallback_on_fail,
            for_auto_enqueue=self._for_auto_enqueue,
            high_quality=self._high_quality,
        )
        self._manager._finish_job(self._source_path, result, geometry_summary)


class NativeThumbnailQueueManager(QObject):
    """
    Queue CPU-native thumbnail jobs without blocking the UI thread.

    Emits :pyattr:`job_completed` with :class:`BridgeJobResult` (same contract as bridge).
    """

    job_completed = Signal(object)

    def __init__(self, router: ThumbnailRouter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._router = router
        self._pool = QThreadPool.globalInstance()
        self._lock = threading.Lock()
        self._in_flight_keys: set[str] = set()
        self._fallback_on_fail: dict[str, bool] = {}
        self._enqueue_closed = False
        self._active_count = 0
        self._geometry_by_key: dict[str, object] = {}

    def in_flight_count(self) -> int:
        """Pending + running native jobs."""
        with self._lock:
            return int(self._active_count)

    def has_source_in_flight(self, source_path: Path) -> bool:
        key = _norm_path_key(source_path)
        with self._lock:
            return key in self._in_flight_keys

    def pop_fallback_on_fail(self, source_path: Path) -> bool:
        key = _norm_path_key(source_path)
        with self._lock:
            return bool(self._fallback_on_fail.pop(key, False))

    def try_enqueue_native(
        self,
        source_path: Path,
        *,
        max_px: int = 512,
        fallback_on_fail: bool = False,
        for_auto_enqueue: bool = False,
        high_quality: bool = False,
    ) -> tuple[bool, str, str]:
        """
        Queue a native thumbnail job when supported.

        Returns ``(ok, message, NativeEnqueueReject)``.
        """
        path = Path(source_path)
        if not self._router.native_supports(path):
            return False, "Native renderer does not support this format.", NativeEnqueueReject.UNSUPPORTED

        health = get_native_renderer_health()
        if not health.available:
            return False, health.jobs_message, NativeEnqueueReject.UNAVAILABLE

        key = _norm_path_key(path)
        with self._lock:
            if self._enqueue_closed:
                return False, "Application is shutting down.", NativeEnqueueReject.SHUTDOWN
            if key in self._in_flight_keys:
                return (
                    False,
                    "Native thumbnail job already queued for this file.",
                    NativeEnqueueReject.DUPLICATE,
                )
            if self._active_count >= MAX_NATIVE_IN_FLIGHT:
                return (
                    False,
                    "Native thumbnail queue is full; try again shortly.",
                    NativeEnqueueReject.CAP,
                )
            self._in_flight_keys.add(key)
            self._fallback_on_fail[key] = bool(fallback_on_fail)
            self._active_count += 1

        import uuid

        job_id = str(uuid.uuid4())
        runnable = _NativeThumbRunnable(
            self,
            path,
            job_id,
            max_px=max_px,
            fallback_on_fail=fallback_on_fail,
            for_auto_enqueue=for_auto_enqueue,
            high_quality=high_quality,
        )
        self._pool.start(runnable)
        logger.debug("Native enqueue thumbnail job %s (source=%s)", job_id, path)
        return True, "", NativeEnqueueReject.OK

    def pop_geometry_summary(self, source_path: Path) -> object:
        """Remove and return render-time geometry summary for *source_path*, if any."""
        from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary

        key = _norm_path_key(source_path)
        with self._lock:
            raw = self._geometry_by_key.pop(key, None)
        if isinstance(raw, AssetMetadataSummary):
            return raw
        return None

    def _finish_job(
        self,
        source_path: Path,
        result: BridgeJobResult,
        geometry_summary: object = None,
    ) -> None:
        key = _norm_path_key(source_path)
        with self._lock:
            self._in_flight_keys.discard(key)
            self._active_count = max(0, self._active_count - 1)
            if geometry_summary is not None:
                self._geometry_by_key[key] = geometry_summary
        try:
            self.job_completed.emit(result)
        except RuntimeError:
            logger.debug("native job_completed emit aborted: signal source deleted")

    @Slot(object)
    def _deliver_result(self, result: object) -> None:
        """Unused slot placeholder for future QMetaObject delivery."""
        if isinstance(result, BridgeJobResult):
            self.job_completed.emit(result)

    def request_stop(self) -> None:
        """Stop accepting new native jobs (shutdown)."""
        with self._lock:
            self._enqueue_closed = True

    def shutdown(self) -> None:
        """Close enqueue; in-flight pool jobs may still complete."""
        self.request_stop()
