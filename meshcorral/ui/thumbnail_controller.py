"""Load and cache Blender/raster thumbnails for the table and gallery (async, no UI blocking)."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from PySide6.QtCore import QRunnable, QThreadPool, Qt, QSize, Signal, Slot, QObject
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.thumb_index import (
    BlenderThumbPathIndex,
    ThumbFailureInfo,
    _norm_path_key,
    inspector_metadata_format,
)
from meshcorral.app.config import SUPPORTED_IMAGE_EXTENSIONS
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumb_paint_diagnostics import ThumbPaintDiagnostics
from meshcorral.ui.gallery_scaled_pixmap_cache import (
    GalleryScaledPixmapCache,
    gallery_scaled_pixmap_key,
)
from meshcorral.ui.thumbnail_pixmap_cache import ThumbnailPixmapLRUCache
from meshcorral.ui.thumbnail_ready_cache import ThumbnailReadyCache
from meshcorral.ui.ui_scroll_profiler import UiScrollProfiler
from meshcorral.ui.thumbnails.placeholder_factory import build_format_card_icon
from meshcorral.ui.thumbnails.thumbnail_confidence import confidence_state_for
from meshcorral.ui.thumbnails.thumbnail_style_rules import default_style_rules
from meshcorral.ui.thumbnails.thumb_quality_profiles import ThumbQualityProfile, default_quality_profile
from meshcorral.ui.thumbnails.unsupported_visuals import format_card_title, resolve_unsupported_visual
from meshcorral.utils.path_perf import (
    PRIME_PERF_MAX_DECODE_WORKERS,
    RemoteThrottleProfile,
    remote_throttle_profile,
)

if TYPE_CHECKING:
    from meshcorral.ui.file_table_model import FileTableModel
    from meshcorral.ui.gallery_list_model import GalleryListModel

logger = logging.getLogger(__name__)

# Allowed display sizes (matches :class:`~meshcorral.services.settings_service.SettingsService`).
_DEFAULT_THUMB_PX: Final[int] = 48
_TIMING_LOGS: Final[bool] = os.environ.get("ROUNDUP_TIMING", "").strip() == "1"


def _coerce_table_thumb_px(px: int) -> int:
    """
    Dedicated decode size for the file table Thumb column.

    This is intentionally **not** tied to gallery zoom pixels (48/96/160/256) so dense
    list views remain readable regardless of gallery settings.
    """
    if px in (72, 88, 96):
        return int(px)
    return 96


TABLE_THUMB_PX: Final[int] = _coerce_table_thumb_px(
    int(os.environ.get("ROUNDUP_TABLE_THUMB_PX", "96").strip() or "96")
)


_PURPOSE_TABLE: Final[str] = "table"
_PURPOSE_GALLERY: Final[str] = "gallery"

_paint_context = threading.local()


def _in_paint_context() -> bool:
    return bool(getattr(_paint_context, "active", False))


class _ImageLoadSignals(QObject):
    """Thread → main: loaded image (or None), plus stale-decode notifications."""

    # purpose, normalized path key, abs source path on disk, QImage | None
    image_ready = Signal(str, str, str, object)
    # purpose, normalized path key, decode px — emitted when the viewport epoch advanced
    image_stale = Signal(str, str, int)


class _RasterReadySignals(QObject):
    """Thread → main: raster sources validated on disk (no decode)."""

    paths_ready = Signal(object)  # list[Path]


class _RasterReadyRunnable(QRunnable):
    """Off-UI-thread existence check for raster sources (Prime v0.5)."""

    def __init__(
        self,
        records: list[FileRecord],
        sigs: _RasterReadySignals,
        *,
        epoch: int = 0,
        current_epoch_fn: Callable[[], int] | None = None,
    ) -> None:
        super().__init__()
        self._records = list(records)
        self._sigs = sigs
        self._epoch = int(epoch)
        self._current_epoch_fn = current_epoch_fn

    def _is_stale(self) -> bool:
        if self._current_epoch_fn is None:
            return False
        try:
            return int(self._current_epoch_fn()) > self._epoch
        except (TypeError, ValueError):
            return False

    def run(self) -> None:
        if self._is_stale():
            return
        paths: list[Path] = []
        for record in self._records:
            if self._is_stale():
                return
            try:
                if record.path.is_file():
                    paths.append(record.path)
            except OSError:
                continue
        if self._is_stale():
            return
        self._sigs.paths_ready.emit(paths)


class _LoadRunnable(QRunnable):
    def __init__(
        self,
        *,
        purpose: str,
        key: str,
        abs_thumb: str,
        px: int,
        sigs: _ImageLoadSignals,
        epoch: int = 0,
        current_epoch_fn: Callable[[], int] | None = None,
    ) -> None:
        super().__init__()
        self._purpose = str(purpose)
        self._key = key
        self._path = abs_thumb
        self._px = int(px)
        self._sigs = sigs
        self._epoch = int(epoch)
        self._current_epoch_fn = current_epoch_fn

    @property
    def epoch(self) -> int:
        """Snapshot of the viewport epoch when this runnable was queued."""
        return self._epoch

    def _is_stale(self) -> bool:
        if self._current_epoch_fn is None:
            return False
        try:
            return int(self._current_epoch_fn()) > self._epoch
        except (TypeError, ValueError):
            return False

    def run(self) -> None:
        if self._is_stale():
            self._sigs.image_stale.emit(self._purpose, self._key, int(self._px))
            return
        img: QImage | None = None

        # Prefer Pillow when available (more formats + better error behavior),
        # but fall back to Qt's QImage loader if Pillow is not installed.
        try:
            from PIL import Image  # type: ignore[import-not-found]

            try:
                with Image.open(self._path) as im:
                    im.load()
                    im2 = im.copy()
                    px = int(self._px)
                    if px > 0:
                        im2.thumbnail((px, px))
                    rgba = im2.convert("RGBA")
                    # Encode to PNG bytes, then decode into QImage for Qt consumption.
                    import io

                    buf = io.BytesIO()
                    rgba.save(buf, format="PNG")
                    pm = QPixmap()
                    # Use QPixmap for in-memory PNG bytes (more reliable bindings than QImage.fromData here).
                    if not pm.loadFromData(buf.getvalue(), "PNG"):
                        img = None
                    else:
                        img = pm.toImage()
            except (OSError, ValueError, TypeError) as e:
                logger.debug("Pillow load error %s: %s", self._path, e)
                img = None
        except ImportError:
            img = None

        if img is None:
            try:
                img = QImage(self._path)
            except (OSError, TypeError) as e:
                logger.debug("QImage load error %s: %s", self._path, e)
                self._sigs.image_ready.emit(self._purpose, self._key, self._path, None)
                return
        if img.isNull():
            self._sigs.image_ready.emit(self._purpose, self._key, self._path, None)
            return

        # Scale off the UI thread; QPixmap conversion stays on the main thread.
        px = self._px
        if px > 0:
            img2 = img.scaled(
                px,
                px,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            img2 = img
        self._sigs.image_ready.emit(self._purpose, self._key, self._path, img2)


def _coerce_display_px(px: int) -> int:
    if px in (48, 96, 160, 256):
        return px
    return _DEFAULT_THUMB_PX


class ThumbnailViewController(QObject):
    """
    Resolve :class:`BlenderThumbPathIndex` thumbnails and decode raster files off the UI thread.

    - **Gallery/table** both use DecorationRole-driven async loads.
    - **Gallery** pixel size tracks the UI zoom dropdown (48/96/160/256).
    - **Table** uses a stable larger decode target so list rows stay readable independently
      from gallery zoom.
    """

    display_pixel_size_changed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._index = BlenderThumbPathIndex()
        self._gallery_icon_cache: "OrderedDict[str, QIcon]" = OrderedDict()
        self._table_icon_cache: "OrderedDict[str, QIcon]" = OrderedDict()
        self._decoding_keys: set[str] = set()
        self._default_icon = QIcon()
        self._failed_table: set[str] = set()
        self._failed_gallery: set[str] = set()
        self._health_icons: dict[tuple[ThumbHealth, str], QIcon] = {}
        self._card_icon_cache: dict[tuple[str, str, int, str], QIcon] = {}
        self._gallery_decoration_cache: dict[str, QIcon] = {}
        self._gallery_decoration_cache_max: int = 4096
        self._queued_keys: set[str] = set()
        self._generating_keys: set[str] = set()
        # Debug-friendly cache stats (counts only; no heavy introspection).
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._loads_started: int = 0
        self._loads_succeeded: int = 0
        self._loads_failed: int = 0
        self._sigs = _ImageLoadSignals(self)
        self._sigs.image_ready.connect(self._on_image_ready, Qt.QueuedConnection)
        self._sigs.image_stale.connect(self._on_image_stale, Qt.QueuedConnection)
        self._raster_ready_sigs = _RasterReadySignals(self)
        self._raster_ready_sigs.paths_ready.connect(
            self._on_raster_paths_ready, Qt.QueuedConnection
        )
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._primer_pool = QThreadPool(self)
        self._primer_pool.setMaxThreadCount(1)
        self._model: FileTableModel | None = None
        self._gallery_model: GalleryListModel | None = None
        self._lock = threading.Lock()
        self._display_px: int = _DEFAULT_THUMB_PX
        self._table_px: int = int(TABLE_THUMB_PX)
        self._table_default_pixmap: QPixmap | None = None
        self._prime_perf: bool = False
        self._coalesce_refresh: Callable[[str], None] | None = None
        self._decode_status_fn: Callable[[], None] | None = None
        self._record_visible_fn: Callable[[FileRecord], bool] | None = None
        self._visible_rows_fn: Callable[[], list[int]] | None = None
        self._ready_cache = ThumbnailReadyCache()
        self._pixmap_lru = ThumbnailPixmapLRUCache()
        self._gallery_scaled = GalleryScaledPixmapCache()
        self._paint_diag = ThumbPaintDiagnostics()
        self._quality_profile: ThumbQualityProfile = default_quality_profile()
        self._theme_mode: str = "dark"
        self._working_set_count: int = 0
        self._throttle_profile: RemoteThrottleProfile = remote_throttle_profile(False)
        self._epoch_fn: Callable[[], int] | None = None
        self._stale_drops: int = 0
        # Deterministic shutdown flag: once set, no new decode/primer work is queued,
        # in-flight completion slots become no-ops, and the pools are drained with a
        # bounded wait by :meth:`request_shutdown` (called from MainWindow.closeEvent).
        self._shutting_down: bool = False
        self._fast_scroll_suppressed: bool = False

    @staticmethod
    def _pixmap_cache_key(norm_path_key: str, px: int) -> str:
        """LRU key: normalized source path plus decode pixel size."""
        return f"{norm_path_key}|{int(px)}"

    def _has_cached_pixmap(self, norm_path_key: str) -> bool:
        """True when any decode size for *norm_path_key* is in the pixmap LRU."""
        for px in (self._display_px, self._table_px):
            if self._pixmap_lru.peek(self._pixmap_cache_key(norm_path_key, px)) is not None:
                return True
        return False

    def _sync_paint_cache_stats(self) -> None:
        self._paint_diag.update_cache_stats(self._pixmap_lru.stats())

    def _clear_gallery_decoration_cache(self) -> None:
        """Drop cached gallery :class:`QIcon` decorations (after index or zoom changes)."""
        with self._lock:
            self._gallery_decoration_cache.clear()
        self._gallery_scaled.clear()

    def gallery_scaled_cache_stats(self) -> dict[str, int]:
        """Scaled pixmap cache counters (tests / diagnostics)."""
        return self._gallery_scaled.stats()

    def gallery_paint_pixmap(self, record: FileRecord, px: int) -> QPixmap:
        """
        Display-ready pixmap for gallery delegate paint (cached, UI thread only).

        Does not read source files from disk; uses decode LRU and scaled pixmap cache.
        """
        side = max(8, int(px))
        norm = _norm_path_key(record.path)
        scaled_key = gallery_scaled_pixmap_key(
            norm,
            side,
            size_bytes=record.size_bytes,
            modified_time=record.modified_time,
        )
        cached = self._gallery_scaled.get(scaled_key)
        if cached is not None and not cached.isNull():
            return cached

        with UiScrollProfiler.measure_pixmap_scale():
            decode_key = self._pixmap_cache_key(norm, side)
            pm = self._pixmap_lru.get(decode_key)
            if pm is None or pm.isNull():
                icon = self.decoration_for(record)
                if icon is None or icon.isNull():
                    icon = self.resolve_default_icon()
                pm = icon.pixmap(side, side)
            if pm is None or pm.isNull():
                pm = self.resolve_default_icon().pixmap(side, side)
            if pm is not None and not pm.isNull():
                self._gallery_scaled.put(scaled_key, pm)
        return pm

    def _invalidate_gallery_decoration_for_key(self, path_key: str) -> None:
        """Drop cached gallery decorations for one normalized source path."""
        prefix = f"{path_key}|"
        with self._lock:
            drop = [k for k in self._gallery_decoration_cache if k.startswith(prefix)]
            for k in drop:
                self._gallery_decoration_cache.pop(k, None)
        self._gallery_scaled.remove_matching_path_prefix(path_key)

    def _gallery_decoration_cache_key(self, record: FileRecord) -> str:
        """Stable key for a gallery decoration given current visual/decode state."""
        key = _norm_path_key(record.path)
        ready = int(self._ready_cache.is_ready(record.path))
        if _in_paint_context() and self._prime_perf:
            with self._lock:
                failed = key in self._failed_gallery
                decoding = any(
                    dk == key or dk.startswith(f"{key}|") for dk in self._decoding_keys
                )
                has_pm = self._has_cached_pixmap(key)
            if failed:
                token = ThumbVisualState.FAILED.value
            elif has_pm:
                token = ThumbVisualState.READY.value
            elif decoding:
                token = ThumbVisualState.DECODING.value
            elif ready:
                token = "ready_decode"
            else:
                token = ThumbVisualState.PLACEHOLDER.value
            return f"{key}|{int(self._display_px)}|{token}|{ready}"

        vs = self.visual_state(record)
        health = self.thumb_health(record)
        return f"{key}|{int(self._display_px)}|{vs.value}|{ready}|{health.name}"

    def _store_gallery_decoration_cache(self, cache_key: str, icon: QIcon) -> None:
        with self._lock:
            if len(self._gallery_decoration_cache) >= self._gallery_decoration_cache_max:
                self._gallery_decoration_cache.clear()
            self._gallery_decoration_cache[cache_key] = icon

    def _note_pixmap_cache_reset(self) -> None:
        if self._prime_perf:
            self._paint_diag.note_cache_reset()

    def set_queued_source_paths(self, paths: list[Path]) -> None:
        """
        Update queued thumbnail source paths (waiting to run).

        This is UI state only. The caller is responsible for providing a best-effort snapshot.
        """
        keys = {_norm_path_key(p) for p in paths}
        with self._lock:
            if keys == self._queued_keys:
                return
            changed = self._queued_keys ^ keys
            self._queued_keys = set(keys)
            if not self._prime_perf:
                self._card_icon_cache.clear()
        if self._prime_perf:
            return
        for k in changed:
            self._emit_rows_for_path_key(k)

    def set_generating_source_path(self, path: Path | None) -> None:
        """
        Update the currently generating thumbnail source path.

        Blender queue runs one job at a time, so this is tracked as a single active key.
        """
        key = _norm_path_key(path) if path is not None else None
        with self._lock:
            prev = next(iter(self._generating_keys), None) if self._generating_keys else None
            if prev == key:
                return
            changed: set[str] = set()
            if prev is not None:
                changed.add(prev)
            self._generating_keys.clear()
            if key is not None:
                self._generating_keys.add(key)
                changed.add(key)
            if not self._prime_perf:
                self._card_icon_cache.clear()
        if self._prime_perf:
            return
        for k in changed:
            self._emit_rows_for_path_key(k)

    def queued_count(self) -> int:
        with self._lock:
            return int(len(self._queued_keys))

    def generating_count(self) -> int:
        with self._lock:
            return int(len(self._generating_keys))

    def decoding_count(self) -> int:
        """Rows with an in-flight async pixmap decode (gallery or table)."""
        with self._lock:
            return int(len(self._decoding_keys))

    def visual_state(self, record: FileRecord) -> ThumbVisualState:
        """
        Unified presentation state for browse thumbnails (geometry and raster).

        Does not perform disk I/O.
        """
        key = _norm_path_key(record.path)
        ext = (record.extension or record.path.suffix).lower().strip()
        with self._lock:
            if key in self._failed_gallery or key in self._failed_table:
                return ThumbVisualState.FAILED
            if any(dk == key or dk.startswith(f"{key}|") for dk in self._decoding_keys):
                return ThumbVisualState.DECODING
            if self._has_cached_pixmap(key):
                return ThumbVisualState.READY
            if key in self._gallery_icon_cache or key in self._table_icon_cache:
                return ThumbVisualState.READY
            if key in self._generating_keys or key in self._queued_keys:
                return ThumbVisualState.QUEUED

        if ext in SUPPORTED_IMAGE_EXTENSIONS:
            if self._ready_cache.is_ready(record.path):
                return ThumbVisualState.PLACEHOLDER
            return ThumbVisualState.PLACEHOLDER

        health = self.resolve_thumb_health(record)
        if health == ThumbHealth.FAILED_THUMBNAIL:
            return ThumbVisualState.FAILED
        if health == ThumbHealth.UNSUPPORTED:
            return ThumbVisualState.UNSUPPORTED
        if self._ready_cache.is_ready(record.path):
            return ThumbVisualState.PLACEHOLDER
        if self._prime_perf:
            return ThumbVisualState.PLACEHOLDER
        if health == ThumbHealth.HAS_THUMBNAIL:
            return ThumbVisualState.PLACEHOLDER
        return ThumbVisualState.PLACEHOLDER

    def thumb_row_decode_flags(self, record: FileRecord) -> tuple[bool, bool, bool]:
        """Return (generating, queued, decoding) for thumbnail UX in the inspector."""
        key = _norm_path_key(record.path)
        with self._lock:
            generating = key in self._generating_keys
            queued = key in self._queued_keys
            decoding = any(
                dk == key or dk.startswith(f"{key}|") for dk in self._decoding_keys
            )
        return generating, queued, decoding

    def prime_raster_ready_async(self, records: list[FileRecord]) -> None:
        """
        Validate raster sources off the UI thread and mark READY (no pixmap decode).

        Row refresh is batched via :meth:`_request_row_refresh` when priming completes.
        Prime v0.7: chunks remote scans into smaller primer batches and stamps the
        current viewport epoch on each runnable so scrolling cancels stale work.

        Once :meth:`request_shutdown` has been called this method is a no-op so the
        primer pool is not re-fed during application teardown.
        """
        if not records or self._shutting_down or self._fast_scroll_suppressed:
            return
        batch_size = max(1, int(self._throttle_profile.primer_batch_size))
        epoch = self.current_epoch()
        for start in range(0, len(records), batch_size):
            chunk = records[start : start + batch_size]
            if not chunk:
                continue
            self._primer_pool.start(
                _RasterReadyRunnable(
                    chunk,
                    self._raster_ready_sigs,
                    epoch=epoch,
                    current_epoch_fn=self._epoch_fn,
                )
            )

    @Slot(object)
    def _on_raster_paths_ready(self, paths: object) -> None:
        if self._shutting_down:
            return
        if not isinstance(paths, list):
            return
        for item in paths:
            if not isinstance(item, Path):
                continue
            if self._ready_cache.mark_ready_raster(item):
                self._request_row_refresh(_norm_path_key(item))

    def set_working_set_count(self, count: int) -> None:
        """Inform placeholder padding when the indexed working set is very large."""
        self._working_set_count = max(0, int(count))

    def quality_profile(self) -> ThumbQualityProfile:
        """Active thumbnail quality tier (Prime v1.0)."""
        return self._quality_profile

    def set_quality_profile(self, profile: ThumbQualityProfile) -> None:
        """Switch quality tier and clear card caches."""
        self._quality_profile = profile
        with self._lock:
            self._card_icon_cache.clear()

    def theme_mode(self) -> str:
        """Active UI theme for painted thumbnails (``dark`` or ``light``)."""
        return self._theme_mode if self._theme_mode in ("dark", "light") else "dark"

    def set_theme_mode(self, theme_mode: str) -> None:
        """Switch light/dark card/badge colors and clear painted caches."""
        mode = theme_mode if theme_mode in ("dark", "light") else "dark"
        if mode == self._theme_mode:
            return
        self._theme_mode = mode
        with self._lock:
            self._card_icon_cache.clear()
            self._health_icons.clear()

    def _card_icon_for(
        self,
        record: FileRecord,
        *,
        purpose: str,
        px: int,
        health: ThumbHealth | None = None,
        deferred: bool = False,
        count_placeholder_paint: bool = False,
    ) -> QIcon:
        """
        Render a lightweight "format card" icon for non-thumbnail states.

        Prime v1.0: unified style rules, per-format identity, and confidence badges.
        """
        ext = (record.extension or record.path.suffix or "").lower().strip()
        title = format_card_title(ext)
        visual = self.visual_state(record)
        health_resolved = health if health is not None else self.thumb_health(record)
        generating = False
        if visual == ThumbVisualState.QUEUED:
            with self._lock:
                generating = _norm_path_key(record.path) in self._generating_keys
        use_deferred = bool(deferred) or (
            self._prime_perf and visual == ThumbVisualState.PLACEHOLDER
        )
        bridge_err: str | None = None
        if health_resolved == ThumbHealth.FAILED_THUMBNAIL:
            info = self.thumb_failure_info(record)
            if info is not None and info.error_message:
                bridge_err = str(info.error_message)
        confidence = confidence_state_for(
            visual,
            health=health_resolved,
            generating=generating,
            deferred=use_deferred,
            bridge_error_message=bridge_err,
        )
        identity = resolve_unsupported_visual(
            ext,
            health=health_resolved,
            visual=visual,
            size_bytes=int(record.size_bytes) if record.size_bytes is not None else 0,
            deferred=use_deferred,
            bridge_error_message=bridge_err,
        )
        cache_key = (
            purpose,
            title,
            int(px),
            confidence.value,
            identity.kind.value,
            self._theme_mode,
        )
        with self._lock:
            cached = self._card_icon_cache.get(cache_key)
        if cached is not None and not cached.isNull():
            return cached

        if count_placeholder_paint and self._prime_perf:
            self._paint_diag.note_placeholder()
            self._paint_diag.note_thumbnail_widget_rebuild()

        icon = build_format_card_icon(
            record,
            visual=visual,
            health=health_resolved,
            px=int(px),
            generating=generating,
            deferred=use_deferred,
            working_set_count=self._working_set_count,
            theme_mode=self._theme_mode,
            bridge_error_message=bridge_err,
        )
        with self._lock:
            self._card_icon_cache[cache_key] = icon
        return icon

    def display_pixel_size(self) -> int:
        """Current thumbnail target size in pixels (width/height, aspect preserved)."""
        return self._display_px

    def set_display_pixel_size(self, px: int) -> None:
        """
        Set size for scaled thumbs and :meth:`size_hint`; clears the icon cache if changed.
        *px* must be one of 48, 96, 160, 256; otherwise 48 is used.
        """
        px = _coerce_display_px(int(px))
        if px == self._display_px:
            return
        self._display_px = px
        with self._lock:
            self._gallery_icon_cache.clear()
            self._failed_gallery.clear()
            self._decoding_keys.clear()
        self._pixmap_lru.clear()
        self._note_pixmap_cache_reset()
        self._clear_gallery_decoration_cache()
        self._reset_cache_stats()
        self._emit_table_thumb_metrics_changed()
        if self._prime_perf:
            self._emit_visible_metrics_refresh()
        else:
            gm = self._gallery_model
            if gm is not None:
                gm.emit_all_item_metrics()
        self.display_pixel_size_changed.emit(self._display_px)

    def _reset_cache_stats(self) -> None:
        self._cache_hits = 0
        self._cache_misses = 0
        self._loads_started = 0
        self._loads_succeeded = 0
        self._loads_failed = 0

    def cache_stats(self) -> dict[str, int | float]:
        """Lightweight counters for troubleshooting large libraries."""
        with self._lock:
            failed_n = len(self._failed_gallery) + len(self._failed_table)
            inflight_n = len(self._decoding_keys)
        lru = self._pixmap_lru.stats()
        return {
            "cache_items": int(lru.get("cache_items", 0)),
            "cache_mb": float(lru.get("cache_mb", 0.0)),
            "pending_loads": int(inflight_n),
            "failed_items": int(failed_n),
            "cache_hits": int(self._cache_hits),
            "cache_misses": int(self._cache_misses),
            "evictions": int(lru.get("evictions", 0)),
            "loads_started": int(self._loads_started),
            "loads_succeeded": int(self._loads_succeeded),
            "loads_failed": int(self._loads_failed),
        }

    def is_shutting_down(self) -> bool:
        """True once :meth:`request_shutdown` has been called."""
        return bool(self._shutting_down)

    def request_shutdown(self, *, timeout_ms: int = 1500) -> None:
        """
        Stop accepting new decode / primer work and drain the pools with a bounded wait.

        Safe to call multiple times. Once invoked:

        * Public enqueue paths (``prime_raster_ready_async``, ``_start_decode``) become
          no-ops.
        * The completion slots (``_on_image_ready``, ``_on_image_stale``,
          ``_on_raster_paths_ready``) early-return so they cannot touch deleted widgets.
        * Both :class:`QThreadPool` instances clear their pending runnables and wait
          up to *timeout_ms* milliseconds for in-flight runnables to finish.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        with self._lock:
            self._decoding_keys.clear()
            self._queued_keys.clear()
            self._generating_keys.clear()
        try:
            self._pool.clear()
        except (RuntimeError, AttributeError) as exc:
            logger.debug("decode pool clear failed during shutdown: %s", exc)
        try:
            self._primer_pool.clear()
        except (RuntimeError, AttributeError) as exc:
            logger.debug("primer pool clear failed during shutdown: %s", exc)
        timeout = max(0, int(timeout_ms))
        decode_done = True
        primer_done = True
        try:
            decode_done = bool(self._pool.waitForDone(timeout))
        except (RuntimeError, AttributeError) as exc:
            logger.debug("decode pool waitForDone failed during shutdown: %s", exc)
        try:
            primer_done = bool(self._primer_pool.waitForDone(timeout))
        except (RuntimeError, AttributeError) as exc:
            logger.debug("primer pool waitForDone failed during shutdown: %s", exc)
        if not decode_done:
            logger.info(
                "ThumbnailViewController: decode pool did not drain in %s ms (active=%s)",
                timeout,
                int(self._pool.activeThreadCount()),
            )
        if not primer_done:
            logger.info(
                "ThumbnailViewController: primer pool did not drain in %s ms (active=%s)",
                timeout,
                int(self._primer_pool.activeThreadCount()),
            )

    def clear_thumbnail_cache(self) -> None:
        """Clear in-memory thumbnail icon cache (keeps the Blender index)."""
        with self._lock:
            self._gallery_icon_cache.clear()
            self._table_icon_cache.clear()
            self._card_icon_cache.clear()
            self._queued_keys.clear()
            self._generating_keys.clear()
            self._decoding_keys.clear()
            self._failed_gallery.clear()
            self._failed_table.clear()
        self._pixmap_lru.clear()
        self._note_pixmap_cache_reset()
        self._clear_gallery_decoration_cache()
        self._ready_cache.clear()
        self._reset_cache_stats()
        self._paint_diag.reset()
        if self._prime_perf:
            self._emit_visible_metrics_refresh()
        else:
            self._emit_thumb_column_all()

    def set_model(self, model: "FileTableModel | None") -> None:
        """Set the table model so :meth:`emit_thumb_rows_for_path_key` can refresh rows."""
        self._model = model

    def set_gallery_model(self, model: "GalleryListModel | None") -> None:
        """Set the gallery list model to refresh on loads and after index refresh."""
        self._gallery_model = model

    def set_prime_perf_mode(self, enabled: bool, *, network_like: bool = False) -> None:
        """
        Enable production-scale thumbnail UI behavior.

        Defers row repaints via :meth:`set_refresh_coalescer`, limits decode workers
        (smaller cap when *network_like* is True for UNC / mapped shares — Prime v0.7
        remote-mode throttling), and avoids starting pixmap loads for off-screen rows.
        """
        self._prime_perf = bool(enabled)
        self._throttle_profile = remote_throttle_profile(bool(network_like) and self._prime_perf)
        decode_workers = self._throttle_profile.decode_workers if self._prime_perf else 2
        self._pool.setMaxThreadCount(max(1, int(decode_workers)))
        if not self._prime_perf:
            self._paint_diag.reset()
            self._fast_scroll_suppressed = False

    def set_fast_scroll_suppressed(self, suppressed: bool) -> None:
        """
        When True (Prime v0.9), block new pixmap decodes and raster priming during fast scroll.

        In-flight pool work may finish; results for stale epochs are dropped as before.
        """
        was = self._fast_scroll_suppressed
        self._fast_scroll_suppressed = bool(suppressed)
        if self._prime_perf and self._fast_scroll_suppressed and not was:
            self._paint_diag.note_fast_scroll_suppression()

    def is_fast_scroll_suppressed(self) -> bool:
        """Return True when fast-scroll suppression is active."""
        return bool(self._fast_scroll_suppressed)

    def set_epoch_callback(self, fn: Callable[[], int] | None) -> None:
        """Plumb the viewport epoch so background runnables can drop stale work."""
        self._epoch_fn = fn

    def current_epoch(self) -> int:
        """Return the current viewport epoch (0 when no callback is wired)."""
        if self._epoch_fn is None:
            return 0
        try:
            return int(self._epoch_fn())
        except (TypeError, ValueError):
            return 0

    def stale_drop_count(self) -> int:
        """Diagnostic: number of decode results discarded because the epoch advanced."""
        return int(self._stale_drops)

    def throttle_profile(self) -> RemoteThrottleProfile:
        """Active throttle profile (mirrors current prime/network state)."""
        return self._throttle_profile

    def set_refresh_coalescer(self, fn: Callable[[str], None] | None) -> None:
        """When set, row refresh requests are batched (path key) instead of immediate emit."""
        self._coalesce_refresh = fn

    def set_decode_status_callback(self, fn: Callable[[], None] | None) -> None:
        """Optional hook when async decode inflight count changes (footer status)."""
        self._decode_status_fn = fn

    def _notify_decode_activity(self) -> None:
        if self._decode_status_fn is not None:
            self._decode_status_fn()

    def set_record_visible_fn(self, fn: Callable[[FileRecord], bool] | None) -> None:
        """When set with prime perf, pixmap decode runs only for visible records."""
        self._record_visible_fn = fn

    def set_visible_rows_fn(self, fn: Callable[[], list[int]] | None) -> None:
        """Supply current visible row indices for gallery metric refresh (prime perf)."""
        self._visible_rows_fn = fn

    def _request_row_refresh(self, path_key: str) -> None:
        if self._coalesce_refresh is not None:
            self._coalesce_refresh(path_key)
            return
        self._emit_rows_for_path_key(path_key)

    def _record_is_visible(self, record: FileRecord) -> bool:
        if self._record_visible_fn is None:
            return True
        return bool(self._record_visible_fn(record))

    def _should_start_decode(self, record: FileRecord, *, px: int) -> bool:
        # READY gating only applies in prime mode; non-prime paint already inspects disk
        # synchronously via :meth:`_paint_decode_path`.
        if self._fast_scroll_suppressed:
            return False
        if self._prime_perf and not self._ready_cache.is_ready(record.path):
            return False
        if not self._record_is_visible(record):
            return False
        cache_key = self._pixmap_cache_key(_norm_path_key(record.path), px)
        if self._pixmap_lru.peek(cache_key) is not None:
            return False
        with self._lock:
            if cache_key in self._decoding_keys:
                return False
        return True

    def ready_cache(self) -> ThumbnailReadyCache:
        """READY disk thumbnail state (no stat on paint)."""
        return self._ready_cache

    def paint_diagnostics(self) -> ThumbPaintDiagnostics:
        """Prime-mode paint/decode counters."""
        return self._paint_diag

    def _guard_sync_image_load(self, path: str) -> QImage | None:
        """Block synchronous ``QImage`` loads on the UI thread during prime paint."""
        if _in_paint_context() and self._prime_perf:
            self._paint_diag.note_sync_blocked()
            self._paint_diag.maybe_log_summary()
            return None
        try:
            img = QImage(path)
        except (OSError, TypeError):
            return None
        return None if img.isNull() else img

    def _guard_sync_pixmap_load(self, path: str) -> QPixmap | None:
        if _in_paint_context() and self._prime_perf:
            self._paint_diag.note_sync_blocked()
            self._paint_diag.maybe_log_summary()
            return None
        pm = QPixmap(path)
        return None if pm.isNull() else pm

    def _ensure_default_icon(self) -> QIcon:
        if not self._default_icon.isNull():
            return self._default_icon
        app = QApplication.instance()
        if app is not None and app.style() is not None:
            self._default_icon = app.style().standardIcon(
                QStyle.StandardPixmap.SP_FileIcon
            )
        if self._default_icon.isNull():
            self._default_icon = QIcon()
        return self._default_icon

    def refresh_index(self, *, emit_rows: bool = True) -> int:
        """
        Re-scan all ``result.json`` files. Clears the icon cache. Returns number of keys.

        Prefer :meth:`on_job_result` for a single finished job (per-path emits only). Full
        ``emit_all_*`` is intentional here and for explicit Jobs → Refresh thumbnails.

        When *emit_rows* is False, callers refresh visible rows separately (large-folder mode).
        """
        t0 = time.perf_counter()
        n = self._index.refresh()
        if _TIMING_LOGS:
            logger.info("TIMING refresh_index: %.2fms (%s keys)", (time.perf_counter() - t0) * 1000.0, n)
        with self._lock:
            self._gallery_icon_cache.clear()
            self._table_icon_cache.clear()
            self._card_icon_cache.clear()
            self._failed_table.clear()
            self._failed_gallery.clear()
            self._decoding_keys.clear()
        self._pixmap_lru.clear()
        self._note_pixmap_cache_reset()
        self._clear_gallery_decoration_cache()
        self._rebuild_ready_cache_from_index()
        self._reset_cache_stats()
        if emit_rows:
            t1 = time.perf_counter()
            if self._prime_perf:
                self._emit_visible_metrics_refresh()
            else:
                self._emit_thumb_column_all()
            if _TIMING_LOGS:
                logger.info("TIMING emit_thumb_column_all: %.2fms", (time.perf_counter() - t1) * 1000.0)
        return n

    def _rebuild_ready_cache_from_index(self) -> None:
        """Repopulate READY entries from the in-memory index (disk stat once per key)."""
        self._ready_cache.clear()
        for key, thumb in self._index.iter_indexed_thumbnails():
            try:
                src = Path(key)
            except (TypeError, ValueError):
                continue
            self._ready_cache.mark_ready(src, thumb)

    def on_job_result(self, result: BridgeJobResult, *, refresh_ui: bool = True) -> None:
        """
        Call when a bridge job finishes; update the index and optionally refresh UI rows.

        With prime perf, set *refresh_ui* False and route updates through a refresh coalescer
        so pixmap decode happens on the next visible paint pass only.
        """
        t0 = time.perf_counter()
        key = self._index.register_job_result(result)
        if not key:
            return
        with self._lock:
            self._gallery_icon_cache.pop(key, None)
            self._table_icon_cache.pop(key, None)
            if not self._prime_perf:
                self._card_icon_cache.clear()
            self._failed_table.discard(key)
            self._failed_gallery.discard(key)
        self._pixmap_lru.remove_matching_prefix(key)
        self._invalidate_gallery_decoration_for_key(key)
        if result.source_file:
            src = Path(result.source_file)
            if result.status == BridgeJobStatus.COMPLETE:
                self._ready_cache.mark_from_job_result(result)
            else:
                self._ready_cache.mark_not_ready(src)
        t1 = time.perf_counter()
        if refresh_ui:
            self._request_row_refresh(key)
        if _TIMING_LOGS:
            logger.info(
                "TIMING on_job_result: %.2fms (register: %.2fms) key=%s",
                (time.perf_counter() - t0) * 1000.0,
                (t1 - t0) * 1000.0,
                key,
            )

    def resolve_default_icon(self) -> QIcon:
        """The placeholder icon for rows without a thumbnail or while loading."""
        return self._ensure_default_icon()

    def _ensure_table_default_pixmap(self) -> QPixmap:
        """
        Return a table-sized placeholder pixmap (file icon), cached for stable row painting.

        This is intentionally separate from gallery zoom/decoration sizing.
        """
        if self._table_default_pixmap is not None and not self._table_default_pixmap.isNull():
            return self._table_default_pixmap
        side = max(16, min(512, int(self._table_px)))
        pm = self._ensure_default_icon().pixmap(side, side)
        self._table_default_pixmap = pm if not pm.isNull() else QPixmap()
        return self._table_default_pixmap

    def _paint_decode_path(self, record: FileRecord) -> str | None:
        """
        Resolve a thumbnail file path for decode without paint-time disk I/O.

        Prime paint uses :class:`ThumbnailReadyCache` only. Non-paint callers may fall
        back to the in-memory index (still without ``Path.is_file()`` on the UI thread).
        """
        cached = self._ready_cache.get_thumbnail_path(record.path)
        if cached is not None:
            return cached
        ext = record.extension.lower().strip() if record.extension else record.path.suffix.lower()
        is_raster = ext in SUPPORTED_IMAGE_EXTENSIONS
        if _in_paint_context() and self._prime_perf:
            return None
        indexed = self._index.thumbnail_path_indexed(record.path)
        if indexed is not None:
            return str(indexed)
        if _in_paint_context():
            if not self._prime_perf and is_raster:
                return str(record.path)
            return None
        if is_raster:
            return str(record.path)
        return None

    def _placeholder_icon(
        self,
        record: FileRecord,
        *,
        purpose: str,
        px: int,
    ) -> QIcon:
        """Paint-safe placeholder (no index / disk access in prime mode)."""
        return self._card_icon_for(
            record,
            purpose=purpose,
            px=px,
            health=ThumbHealth.PENDING if self._prime_perf else None,
            deferred=True,
            count_placeholder_paint=True,
        )

    def _decoration_for_loaded(
        self,
        record: FileRecord,
        *,
        purpose: str,
        px: int,
        load_path: str,
    ) -> QIcon:
        key = _norm_path_key(record.path)
        cache_key = self._pixmap_cache_key(key, px)
        failed = self._failed_gallery if purpose == _PURPOSE_GALLERY else self._failed_table
        default = (
            self._ensure_default_icon()
            if purpose == _PURPOSE_GALLERY
            else QIcon(self._ensure_table_default_pixmap())
        )
        pm = self._pixmap_lru.get(cache_key)
        if pm is not None and not pm.isNull():
            self._cache_hits += 1
            if self._prime_perf:
                self._paint_diag.note_cache_hit()
                self._sync_paint_cache_stats()
            return QIcon(pm)

        if not self._record_is_visible(record):
            return self._placeholder_icon(record, purpose=purpose, px=px)
        if self._prime_perf and not self._ready_cache.is_ready(record.path):
            return self._placeholder_icon(record, purpose=purpose, px=px)

        self._paint_diag.note_visible_ready()
        with self._lock:
            if key in failed:
                self._cache_misses += 1
                if self._prime_perf:
                    self._paint_diag.note_cache_miss()
                return default
            if cache_key in self._decoding_keys:
                self._cache_misses += 1
                return default

        if not self._should_start_decode(record, px=px):
            return self._placeholder_icon(record, purpose=purpose, px=px)

        self._cache_misses += 1
        if self._prime_perf:
            self._paint_diag.note_cache_miss()
            self._paint_diag.note_deferred_decode()
            self._sync_paint_cache_stats()
        self._start_decode(key, load_path, px=int(px), purpose=purpose)
        return default

    def decoration_for(self, record: FileRecord) -> QIcon:
        """Gallery/icon view decoration (sizes follow :meth:`display_pixel_size`)."""
        _paint_context.active = True
        try:
            deco_key = ""
            if self._prime_perf:
                deco_key = self._gallery_decoration_cache_key(record)
                with self._lock:
                    cached_deco = self._gallery_decoration_cache.get(deco_key)
                if cached_deco is not None and not cached_deco.isNull():
                    self._paint_diag.note_decoration_cache_hit()
                    return cached_deco

            load_path = self._paint_decode_path(record)
            if load_path is None:
                self._cache_misses += 1
                icon = self._placeholder_icon(record, purpose=_PURPOSE_GALLERY, px=int(self._display_px))
            else:
                icon = self._decoration_for_loaded(
                    record,
                    purpose=_PURPOSE_GALLERY,
                    px=int(self._display_px),
                    load_path=load_path,
                )
            if self._prime_perf and deco_key and icon is not None and not icon.isNull():
                self._store_gallery_decoration_cache(deco_key, icon)
            return icon
        finally:
            _paint_context.active = False

    def table_decoration_for(self, record: FileRecord) -> QIcon:
        """
        Table Thumb column decorations (usually larger decode than gallery zoom).

        Qt frequently paints table icons poorly unless :meth:`QTableView.iconSize`
        matches the intended visual size.
        """
        _paint_context.active = True
        try:
            load_path = self._paint_decode_path(record)
            if load_path is None:
                self._cache_misses += 1
                return self._placeholder_icon(record, purpose=_PURPOSE_TABLE, px=int(self._table_px))
            return self._decoration_for_loaded(
                record,
                purpose=_PURPOSE_TABLE,
                px=int(self._table_px),
                load_path=load_path,
            )
        finally:
            _paint_context.active = False

    def table_thumb_pixel_size(self) -> int:
        """Fixed decode/visual target for table thumbnails."""
        return int(self._table_px)

    def _start_decode(self, key: str, abs_path: str, *, px: int, purpose: str) -> None:
        if self._shutting_down or self._fast_scroll_suppressed:
            return
        cache_key = self._pixmap_cache_key(key, px)
        if self._pixmap_lru.peek(cache_key) is not None:
            return
        with self._lock:
            if cache_key in self._decoding_keys:
                return
            failed = self._failed_gallery if purpose == _PURPOSE_GALLERY else self._failed_table
            if key in failed:
                return
            self._decoding_keys.add(cache_key)
        if self._prime_perf:
            self._paint_diag.note_priority_decode_request()
        self._loads_started += 1
        self._notify_decode_activity()
        self._pool.start(
            _LoadRunnable(
                purpose=purpose,
                key=key,
                abs_thumb=abs_path,
                px=int(px),
                sigs=self._sigs,
                epoch=self.current_epoch(),
                current_epoch_fn=self._epoch_fn,
            )
        )

    def _start_gallery_load(self, key: str, abs_path: str) -> None:
        self._start_decode(key, abs_path, px=int(self._display_px), purpose=_PURPOSE_GALLERY)

    def _start_table_load(self, key: str, abs_path: str) -> None:
        self._start_decode(key, abs_path, px=int(self._table_px), purpose=_PURPOSE_TABLE)

    @Slot(str, str, int)
    def _on_image_stale(self, purpose: str, key: str, px: int) -> None:
        """Clear inflight bookkeeping for a decode skipped due to viewport epoch advance."""
        if self._shutting_down:
            return
        cache_key = self._pixmap_cache_key(key, int(px))
        with self._lock:
            self._decoding_keys.discard(cache_key)
        self._stale_drops += 1
        if self._prime_perf:
            self._paint_diag.note_stale_epoch_drop()
        self._notify_decode_activity()
        if self._prime_perf:
            self._paint_diag.maybe_log_summary()

    @Slot(str, str, str, object)
    def _on_image_ready(self, purpose: str, key: str, _thumb_path: str, image: QImage | None) -> None:
        if self._shutting_down:
            return
        t0 = time.perf_counter()
        purpose_s = str(purpose)
        px = int(self._table_px) if purpose_s == _PURPOSE_TABLE else int(self._display_px)
        cache_key = self._pixmap_cache_key(key, px)
        with self._lock:
            self._decoding_keys.discard(cache_key)
        self._notify_decode_activity()

        def _failure() -> None:
            with self._lock:
                if purpose_s == _PURPOSE_TABLE:
                    self._failed_table.add(key)
                else:
                    self._failed_gallery.add(key)

        if image is None or image.isNull():
            _failure()
            self._loads_failed += 1
            self._request_row_refresh(key)
            return

        pm = QPixmap.fromImage(image)
        if pm.isNull():
            _failure()
            self._loads_failed += 1
            self._request_row_refresh(key)
            return

        rules = default_style_rules()
        framed = rules.frame_pixmap_in_square(pm, side_px=px)
        self._pixmap_lru.put(cache_key, framed)
        self._invalidate_gallery_decoration_for_key(key)
        if self._prime_perf:
            self._sync_paint_cache_stats()
        self._loads_succeeded += 1
        self._request_row_refresh(key)

        if _TIMING_LOGS:
            logger.info(
                "TIMING _on_image_ready (UI): %.2fms purpose=%s key=%s",
                (time.perf_counter() - t0) * 1000.0,
                purpose_s,
                key,
            )

    def _emit_rows_for_path_key(self, key: str) -> None:
        m = self._model
        if m is not None:
            m.emit_thumb_rows_for_path_key(key)
        gm = self._gallery_model
        if gm is not None:
            gm.emit_items_for_path_key(key)

    def _emit_table_thumb_metrics_changed(self) -> None:
        m = self._model
        if m is not None:
            m.emit_thumb_column_metrics_changed()

    def _emit_visible_metrics_refresh(self) -> None:
        """Refresh gallery cell metrics for visible rows only (prime perf)."""
        if self._visible_rows_fn is None or self._gallery_model is None:
            return
        from meshcorral.ui.thumb_row_emit import emit_gallery_rows_at_indices

        rows = self._visible_rows_fn()
        if rows:
            emit_gallery_rows_at_indices(self._gallery_model, rows)

    def _emit_thumb_column_all(self) -> None:
        if self._prime_perf:
            self._emit_visible_metrics_refresh()
            return
        m = self._model
        if m is not None:
            m.emit_all_thumb_rows()
        gm = self._gallery_model
        if gm is not None:
            gm.emit_all_item_metrics()

    def size_hint(self) -> QSize:
        """Cell sizing hint for gallery/icon mode (tracks gallery zoom)."""
        return QSize(self._display_px + 8, self._display_px + 4)

    def table_thumb_size_hint(self) -> QSize:
        """Cell sizing hint for the file table Thumb column (stable vs gallery zoom)."""
        tp = max(16, int(self._table_px))
        return QSize(tp + 8, tp + 4)

    def has_index(self, record: FileRecord) -> bool:
        """True if a Blender thumb path is known (file may not be in icon cache yet)."""
        return self._index.has_thumbnail_for(record.path)

    def large_inspector_preview(self, record: FileRecord, max_side: int = 240) -> QPixmap:
        """
        Return a pixmap for the asset inspector: Blender render if indexed, else default file icon.
        Reads the on-disk thumbnail file when available (not the small icon cache).
        """
        side = max(64, min(512, int(max_side)))
        tp = self._index.thumbnail_path_for(record.path)
        if tp is not None:
            img = self._guard_sync_image_load(str(tp))
            if img is not None and not img.isNull():
                pm = QPixmap.fromImage(img)
                if not pm.isNull():
                    rules = default_style_rules()
                    return rules.frame_pixmap_in_square(pm, side_px=side)
        ico = self._ensure_default_icon()
        pm2 = ico.pixmap(side, side)
        return pm2 if not pm2.isNull() else QPixmap()

    def inspector_metadata_bundle(self, record: FileRecord) -> tuple[str, str, str]:
        """Return ``(tags, multiline_body, copy_text)`` from optional bridge ``metadata.json``."""
        mp = self._index.metadata_path_for(record.path)
        return inspector_metadata_format(mp)

    def blender_thumbnail_path(self, record: FileRecord) -> Path | None:
        """Absolute path to indexed Blender ``thumbnail.png`` if available."""
        return self._index.thumbnail_path_for(record.path)

    def resolve_thumb_health(self, record: FileRecord) -> ThumbHealth:
        """Eager thumbnail health from the bridge index (no lazy pending state)."""
        ext = (record.extension or record.path.suffix).lower().strip()
        if ext in SUPPORTED_IMAGE_EXTENSIONS:
            key = _norm_path_key(record.path)
            if self._has_cached_pixmap(key):
                return ThumbHealth.HAS_THUMBNAIL
            with self._lock:
                if key in self._gallery_icon_cache or key in self._table_icon_cache:
                    return ThumbHealth.HAS_THUMBNAIL
            if self._ready_cache.is_ready(record.path):
                return ThumbHealth.PENDING
            return ThumbHealth.PENDING
        return self._index.thumb_health(record)

    def thumb_health(self, record: FileRecord) -> ThumbHealth:
        """Thumbnail coverage for *record* (index + extension; image decode errors do not apply)."""
        if _in_paint_context() and self._prime_perf:
            if self._ready_cache.is_ready(record.path):
                return ThumbHealth.HAS_THUMBNAIL
            return ThumbHealth.PENDING
        return self.resolve_thumb_health(record)

    def thumb_failure_info(self, record: FileRecord) -> ThumbFailureInfo | None:
        """Last failed thumbnail job metadata from the bridge, if any."""
        return self._index.failure_info_for(record.path)

    def failure_output_dir(self, record: FileRecord) -> Path | None:
        """Job output directory for a failed thumbnail run, when it still exists on disk."""
        info = self.thumb_failure_info(record)
        if info is None or not info.output_dir:
            return None
        d = Path(info.output_dir)
        return d if d.is_dir() else None

    def health_badge_icon(self, record: FileRecord) -> QIcon:
        """Small standard icon for table and gallery status badges."""
        health = self.thumb_health(record)
        bridge_err: str | None = None
        if health == ThumbHealth.FAILED_THUMBNAIL:
            info = self.thumb_failure_info(record)
            if info is not None and info.error_message:
                bridge_err = str(info.error_message)
        generating, queued, decoding = self.thumb_row_decode_flags(record)
        return self._badge_icon_for_record(
            health=health,
            visual=self.visual_state(record),
            generating=generating,
            queued=queued,
            decoding=decoding,
            bridge_error_message=bridge_err,
        )

    def health_tooltip(self, record: FileRecord) -> str:
        """Multi-line tooltip: status, paths, and last error when failed."""
        health = self.thumb_health(record)
        lines: list[str] = [health.display_label()]
        if health == ThumbHealth.PENDING:
            lines.append("Scroll into view to load thumbnail status.")
        if health == ThumbHealth.FAILED_THUMBNAIL:
            info = self.thumb_failure_info(record)
            if info is not None:
                if info.output_dir:
                    lines.append(f"Output: {info.output_dir}")
                if info.log_path:
                    lines.append(f"Log: {info.log_path}")
                if info.error_message:
                    lines.append(str(info.error_message))
        return "\n".join(lines)

    def _badge_icon_for_record(
        self,
        *,
        health: ThumbHealth,
        visual: ThumbVisualState,
        generating: bool,
        queued: bool,
        decoding: bool,
        bridge_error_message: str | None,
    ) -> QIcon:
        from meshcorral.ui.thumbnails.badge_paint import build_health_badge_icon
        from meshcorral.ui.thumbnails.badge_styles import resolve_badge_style_kind

        kind = resolve_badge_style_kind(
            health=health,
            visual=visual,
            generating=generating,
            queued=queued,
            decoding=decoding,
            bridge_error_message=bridge_error_message,
        )
        cache_key = (kind.value, self._theme_mode)
        with self._lock:
            cached = self._health_icons.get(cache_key)
        if cached is not None and not cached.isNull():
            return cached
        ico = build_health_badge_icon(
            health,
            theme_mode=self._theme_mode,
            visual=visual,
            generating=generating,
            queued=queued,
            decoding=decoding,
            bridge_error_message=bridge_error_message,
        )
        with self._lock:
            self._health_icons[cache_key] = ico
        return ico

    def _badge_icon(self, health: ThumbHealth) -> QIcon:
        """Legacy health-only badge (tests and simple call sites)."""
        return self._badge_icon_for_record(
            health=health,
            visual=ThumbVisualState.PLACEHOLDER,
            generating=False,
            queued=False,
            decoding=False,
            bridge_error_message=None,
        )
