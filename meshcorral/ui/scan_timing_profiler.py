"""Folder scan timing diagnostics (QoL — long scan visibility, no render pipeline changes)."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final

from meshcorral.app.config import LOG_DIR

logger = logging.getLogger(__name__)

SCAN_TIMING_LOG_PATH = LOG_DIR / "scan_timing.log"
_SLOW_ITEM_THRESHOLD_S: Final[float] = 5.0
_HEARTBEAT_MIN_S: Final[float] = 2.0
_LOG_LOCK = threading.Lock()


@dataclass
class ScanTimingSession:
    """
    Shared scan session state (UI + worker threads).

    Writes JSON lines to ``%LOCALAPPDATA%\\MeshStager\\logs\\scan_timing.log``.
    Heartbeats are throttled; per-file lines are emitted only for slow items (>5s).
    """

    scan_root: str
    asset_mode: str
    include_subfolders: bool
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    _t0: float = field(default_factory=time.perf_counter)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_heartbeat_s: float = field(default=0.0, repr=False)
    files_discovered: int = 0
    files_processed: int = 0
    current_folder: str = ""
    current_extension: str = ""
    _finished: bool = False

    def note_discovery(self, count: int, folder: str) -> None:
        """Update discovery counters from the worker walk heartbeat."""
        with self._lock:
            self.files_discovered = max(self.files_discovered, int(count))
            if folder.strip():
                self.current_folder = folder.strip()

    def note_batch_processed(self, batch_size: int) -> None:
        """Increment processed count when the UI absorbs a scan batch."""
        if batch_size <= 0:
            return
        with self._lock:
            self.files_processed += int(batch_size)

    def set_current_extension(self, ext: str) -> None:
        """Last extension seen on the worker (for heartbeat diagnostics)."""
        if ext.strip():
            with self._lock:
                self.current_extension = ext.strip().lower()

    def note_slow_item(
        self,
        *,
        kind: str,
        path: str,
        elapsed_s: float,
    ) -> None:
        """Log when a single file or folder operation exceeds the slow threshold."""
        if elapsed_s < _SLOW_ITEM_THRESHOLD_S:
            return
        self._append(
            {
                "event": "scan_slow_item",
                "kind": kind,
                "path": path,
                "elapsed_s": round(elapsed_s, 3),
                "warning": f"slow {kind} > {_SLOW_ITEM_THRESHOLD_S:.0f}s",
            }
        )

    def log_heartbeat(self, *, ui_files_indexed: int | None = None) -> None:
        """
        Periodic progress line (at most once per :data:`_HEARTBEAT_MIN_S`).

        *ui_files_indexed* is the main-thread row count when the UI drives the tick.
        """
        if self._finished:
            return
        now = time.perf_counter()
        with self._lock:
            if now - self._last_heartbeat_s < _HEARTBEAT_MIN_S:
                return
            self._last_heartbeat_s = now
            discovered = self.files_discovered
            processed = self.files_processed
            if ui_files_indexed is not None:
                processed = max(processed, int(ui_files_indexed))
            folder = self.current_folder
            ext = self.current_extension
        self._append(
            {
                "event": "scan_heartbeat",
                "files_discovered": discovered,
                "files_processed": processed,
                "current_folder": folder,
                "current_extension": ext,
                "elapsed_s": round(now - self._t0, 3),
            }
        )

    def finish(self, state: str, *, error: str = "") -> None:
        """Write a terminal line (complete, canceled, error)."""
        with self._lock:
            if self._finished:
                return
            self._finished = True
            discovered = self.files_discovered
            processed = self.files_processed
            folder = self.current_folder
            ext = self.current_extension
        elapsed = time.perf_counter() - self._t0
        payload: dict[str, Any] = {
            "event": "scan_finished",
            "state": state,
            "files_discovered": discovered,
            "files_processed": processed,
            "current_folder": folder,
            "current_extension": ext,
            "elapsed_s": round(elapsed, 3),
        }
        if error.strip():
            payload["error"] = error.strip()
        self._append(payload)

    def snapshot_for_log(self) -> dict[str, Any]:
        """Thread-safe snapshot for ad-hoc diagnostic lines."""
        with self._lock:
            return {
                "scan_root": self.scan_root,
                "asset_mode": self.asset_mode,
                "include_subfolders": self.include_subfolders,
                "session_id": self.session_id,
                "files_discovered": self.files_discovered,
                "files_processed": self.files_processed,
                "current_folder": self.current_folder,
                "current_extension": self.current_extension,
                "elapsed_s": round(time.perf_counter() - self._t0, 3),
            }

    def _append(self, fields: dict[str, Any]) -> None:
        base = self.snapshot_for_log()
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **base,
            **fields,
        }
        line = json.dumps(payload, ensure_ascii=False)
        try:
            SCAN_TIMING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_LOCK:
                with SCAN_TIMING_LOG_PATH.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError as exc:
            logger.debug("scan_timing log write failed: %s", exc)

    def log_started(self) -> None:
        """Session start marker."""
        self._append({"event": "scan_started", "state": "started"})


def timed_scan_item(
    session: ScanTimingSession | None,
    *,
    kind: str,
    path: str,
) -> Any:
    """Context manager measuring one filesystem item on the scan worker thread."""

    class _Timed:
        def __enter__(self) -> None:
            self._t0 = time.perf_counter()

        def __exit__(self, *_exc: object) -> None:
            if session is None:
                return
            elapsed = time.perf_counter() - self._t0
            session.note_slow_item(kind=kind, path=path, elapsed_s=elapsed)

    return _Timed()
