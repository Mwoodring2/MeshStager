"""Lightweight gallery scroll / layout timing logs (RC3 UI performance pass)."""

from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from meshcorral.app.config import LOG_DIR, read_branded_env_flag

logger = logging.getLogger(__name__)

SCROLL_TIMING_LOG_PATH = LOG_DIR / "ui_scroll_timing.log"
_LOG_LOCK = threading.Lock()


@dataclass
class _ScrollPaintBucket:
    """Accumulated UI-thread pixmap work between wheel events."""

    pixmap_scale_ms: float = 0.0
    pixmap_scale_calls: int = 0


class UiScrollProfiler:
    """
    Append JSON lines to ``%LOCALAPPDATA%\\MeshStager\\logs\\ui_scroll_timing.log``.

    Tracks wheel handling, visible/total gallery counts, layout rebuilds, and pixmap scaling.
    File logging is off by default; set ``MESHSTAGER_UI_SCROLL_TIMING=1`` to enable.
    """

    _paint_bucket = _ScrollPaintBucket()

    @classmethod
    def file_logging_enabled(cls) -> bool:
        """When false, timing is tracked in memory only (no scroll log spam)."""
        return read_branded_env_flag("UI_SCROLL_TIMING", default=False)
    _last_layout_rebuild_ms: float = 0.0
    _layout_rebuild_count: int = 0

    @classmethod
    def note_layout_rebuild_ms(cls, elapsed_ms: float) -> None:
        """Record time spent in a full gallery model replace (``set_records`` / reset)."""
        ms = max(0.0, float(elapsed_ms))
        cls._last_layout_rebuild_ms = ms
        cls._layout_rebuild_count += 1

    @classmethod
    def last_layout_rebuild_ms(cls) -> float:
        return float(cls._last_layout_rebuild_ms)

    @classmethod
    def layout_rebuild_count(cls) -> int:
        return int(cls._layout_rebuild_count)

    @classmethod
    @contextmanager
    def measure_pixmap_scale(cls) -> Iterator[None]:
        """Context manager for synchronous pixmap/icon scaling on the UI thread."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            cls._paint_bucket.pixmap_scale_ms += elapsed_ms
            cls._paint_bucket.pixmap_scale_calls += 1

    @classmethod
    def consume_pixmap_scale_ms(cls) -> tuple[float, int]:
        """Return accumulated pixmap scale time since last wheel log and reset bucket."""
        bucket = cls._paint_bucket
        ms = float(bucket.pixmap_scale_ms)
        calls = int(bucket.pixmap_scale_calls)
        cls._paint_bucket = _ScrollPaintBucket()
        return ms, calls

    @classmethod
    def log_wheel_event(
        cls,
        *,
        wheel_event_ms: float,
        visible_item_count: int,
        total_gallery_item_count: int,
        view: str,
        scroll_value: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Write one structured timing line for a gallery wheel gesture."""
        pixmap_ms, pixmap_calls = cls.consume_pixmap_scale_ms()
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "gallery_wheel",
            "view": view,
            "wheel_event_ms": round(max(0.0, float(wheel_event_ms)), 3),
            "visible_item_count": int(visible_item_count),
            "total_gallery_item_count": int(total_gallery_item_count),
            "layout_rebuild_ms": round(cls.last_layout_rebuild_ms(), 3),
            "layout_rebuild_count": cls.layout_rebuild_count(),
            "pixmap_scale_ms": round(pixmap_ms, 3),
            "pixmap_scale_calls": pixmap_calls,
            "scroll_value": int(scroll_value),
        }
        if extra:
            payload.update(extra)
        cls._append(payload)

    @classmethod
    def log_layout_rebuild(
        cls,
        *,
        elapsed_ms: float,
        total_gallery_item_count: int,
        reason: str,
    ) -> None:
        """Explicit layout rebuild log (filter apply, zoom change, etc.)."""
        cls.note_layout_rebuild_ms(elapsed_ms)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "gallery_layout_rebuild",
            "layout_rebuild_ms": round(max(0.0, float(elapsed_ms)), 3),
            "total_gallery_item_count": int(total_gallery_item_count),
            "reason": str(reason),
        }
        cls._append(payload)

    @classmethod
    def _append(cls, payload: dict[str, Any]) -> None:
        if not cls.file_logging_enabled():
            return
        line = json.dumps(payload, ensure_ascii=False)
        try:
            SCROLL_TIMING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_LOCK:
                with SCROLL_TIMING_LOG_PATH.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError as exc:
            logger.debug("ui_scroll_timing log write failed: %s", exc)
