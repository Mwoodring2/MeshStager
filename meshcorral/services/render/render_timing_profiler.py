"""Structured timing logs for mesh preview / thumbnail rendering."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from meshcorral.app.config import LOG_DIR

logger = logging.getLogger(__name__)

TIMING_LOG_PATH = LOG_DIR / "render_timing.log"
_LOG_LOCK = threading.Lock()


@dataclass
class RenderTimingRecord:
    """One render attempt with per-stage timings (seconds)."""

    source_path: str
    file_size_mb: float
    extension: str
    is_network_path: bool
    stat_cache_lookup_s: float = 0.0
    geometry_preparation_s: float = 0.0
    preview_preparation_s: float = 0.0
    raster_render_s: float = 0.0
    png_encoding_s: float = 0.0
    stage_copy_s: float = 0.0
    load_import_s: float = 0.0
    geometry_metadata_s: float = 0.0
    preview_proxy_s: float = 0.0
    render_hq_s: float = 0.0
    write_cache_s: float = 0.0
    total_s: float = 0.0
    error_message: str | None = None
    render_mode: str = ""
    used_staging: bool = False
    used_preview_geometry: bool = False
    used_cached_output: bool = False
    staged_path: str | None = None

    def stage_rows(self) -> list[tuple[str, float]]:
        """Return named stages for benchmark tables (excludes total)."""
        return [
            ("stat_cache_lookup", self.stat_cache_lookup_s),
            ("geometry_preparation", self.geometry_preparation_s),
            ("preview_preparation", self.preview_preparation_s),
            ("raster_render", self.raster_render_s),
            ("png_encoding", self.png_encoding_s),
            ("stage_copy", self.stage_copy_s),
            ("load_import", self.load_import_s),
            ("geometry_metadata", self.geometry_metadata_s),
            ("preview_proxy", self.preview_proxy_s),
            ("render_hq", self.render_hq_s),
            ("write_cache", self.write_cache_s),
        ]

    def slowest_stage(self) -> tuple[str, float]:
        """Stage name and duration for the largest non-total segment."""
        rows = self.stage_rows()
        if not rows:
            return ("total", self.total_s)
        name, value = max(rows, key=lambda item: item[1])
        if value <= 0.0 and self.total_s > 0.0:
            return ("total", self.total_s)
        return name, value


@dataclass
class _StageClock:
    """Mutable stage timers for :class:`RenderTimingProfiler`."""

    stat_cache_lookup_s: float = 0.0
    geometry_preparation_s: float = 0.0
    preview_preparation_s: float = 0.0
    raster_render_s: float = 0.0
    png_encoding_s: float = 0.0
    stage_copy_s: float = 0.0
    load_import_s: float = 0.0
    geometry_metadata_s: float = 0.0
    preview_proxy_s: float = 0.0
    render_hq_s: float = 0.0
    write_cache_s: float = 0.0


class RenderTimingProfiler:
    """
    Collect per-stage timings and append one JSON line to ``render_timing.log``.

    Usage::

        profiler = RenderTimingProfiler(source_path)
        with profiler.measure("load_import"):
            mesh = load(...)
        profiler.finish(error_message=None)
    """

    def __init__(
        self,
        source_path: Path,
        *,
        file_size_mb: float,
        extension: str,
        is_network_path: bool,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._source_path = Path(source_path)
        self._file_size_mb = float(file_size_mb)
        self._extension = extension
        self._is_network_path = bool(is_network_path)
        self._status_callback = status_callback
        self._clock = _StageClock()
        self._t0 = time.perf_counter()
        self._render_mode = ""
        self._used_preview_geometry = False
        self._used_staging = False
        self._used_cached_output = False
        self._staged_path: str | None = None
        self._error: str | None = None

    def set_used_preview_geometry(self, used: bool) -> None:
        self._used_preview_geometry = bool(used)

    def set_render_mode(self, mode: str) -> None:
        self._render_mode = str(mode)

    def set_used_staging(self, used: bool, staged_path: Path | None = None) -> None:
        self._used_staging = bool(used)
        if staged_path is not None:
            self._staged_path = str(staged_path)

    def set_used_cached_output(self, used: bool) -> None:
        self._used_cached_output = bool(used)

    def emit_status(self, message: str) -> None:
        """User-facing pipeline status (also logged at INFO)."""
        text = (message or "").strip()
        if not text:
            return
        logger.info("Render pipeline: %s — %s", self._source_path.name, text)
        if self._status_callback is not None:
            try:
                self._status_callback(text)
            except Exception as exc:  # noqa: BLE001 — status must not break render
                logger.debug("status_callback failed: %s", exc)

    def measure(self, stage: str):
        """Context manager that records elapsed time into *stage*."""
        return _MeasureStage(self, stage)

    def add_stage_seconds(self, stage: str, seconds: float) -> None:
        """Add pre-recorded duration to a stage (e.g. nested work)."""
        value = max(0.0, float(seconds))
        if stage in ("stat_cache_lookup", "geometry_preparation", "preview_preparation", "raster_render", "png_encoding"):
            setattr(self._clock, stage + "_s", getattr(self._clock, stage + "_s") + value)
        elif stage == "stage_copy":
            self._clock.stage_copy_s += value
        elif stage == "load_import":
            self._clock.load_import_s += value
        elif stage == "geometry_metadata":
            self._clock.geometry_metadata_s += value
        elif stage in ("preview_proxy", "preview_balanced"):
            self._clock.preview_proxy_s += value
        elif stage == "render_hq":
            self._clock.render_hq_s += value
        elif stage == "write_cache":
            self._clock.write_cache_s += value

    def finish(
        self,
        *,
        error_message: str | None = None,
        write_log: bool = True,
    ) -> RenderTimingRecord:
        """Build record, optionally append to log file, return it."""
        if error_message:
            self._error = str(error_message)
        total_s = time.perf_counter() - self._t0
        record = RenderTimingRecord(
            source_path=str(self._source_path),
            file_size_mb=self._file_size_mb,
            extension=self._extension,
            is_network_path=self._is_network_path,
            stat_cache_lookup_s=self._clock.stat_cache_lookup_s,
            geometry_preparation_s=self._clock.geometry_preparation_s,
            preview_preparation_s=self._clock.preview_preparation_s,
            raster_render_s=self._clock.raster_render_s,
            png_encoding_s=self._clock.png_encoding_s,
            used_preview_geometry=self._used_preview_geometry,
            stage_copy_s=self._clock.stage_copy_s,
            load_import_s=self._clock.load_import_s,
            geometry_metadata_s=self._clock.geometry_metadata_s,
            preview_proxy_s=self._clock.preview_proxy_s,
            render_hq_s=self._clock.render_hq_s,
            write_cache_s=self._clock.write_cache_s,
            total_s=total_s,
            error_message=self._error,
            render_mode=self._render_mode,
            used_staging=self._used_staging,
            used_cached_output=self._used_cached_output,
            staged_path=self._staged_path,
        )
        if write_log:
            _append_timing_log(record)
            _log_timing_summary(record)
        return record


class _MeasureStage:
    def __init__(self, profiler: RenderTimingProfiler, stage: str) -> None:
        self._profiler = profiler
        self._stage = stage
        self._t0 = 0.0

    def __enter__(self) -> _MeasureStage:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = time.perf_counter() - self._t0
        self._profiler.add_stage_seconds(self._stage, elapsed)


def _log_timing_summary(record: RenderTimingRecord) -> None:
    stage, sec = record.slowest_stage()
    logger.info(
        "Render timing total=%.3fs slowest=%s(%.3fs) path=%s network=%s mode=%s cached=%s err=%s",
        record.total_s,
        stage,
        sec,
        record.source_path,
        record.is_network_path,
        record.render_mode,
        record.used_cached_output,
        record.error_message or "",
    )


def _append_timing_log(record: RenderTimingRecord) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        payload = asdict(record)
        payload["logged_at"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(payload, sort_keys=True)
        with _LOG_LOCK:
            with TIMING_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError as exc:
        logger.warning("Could not write render timing log: %s", exc)


def format_benchmark_table(records: list[RenderTimingRecord]) -> str:
    """Aggregate stage totals across records for benchmark script output."""
    totals: dict[str, float] = {
        "stage_copy": 0.0,
        "load_import": 0.0,
        "geometry_metadata": 0.0,
        "preview_proxy": 0.0,
        "render_hq": 0.0,
        "write_cache": 0.0,
    }
    for rec in records:
        for name, value in rec.stage_rows():
            totals[name] = totals.get(name, 0.0) + value
    rows = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    lines = ["Stage totals (seconds, sorted slowest first):", f"{'Stage':<22} {'Total(s)':>10} {'Avg(s)':>10}"]
    count = max(1, len(records))
    for name, total in rows:
        lines.append(f"{name:<22} {total:10.3f} {total / count:10.3f}")
    return "\n".join(lines)
