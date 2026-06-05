"""Prime-mode paint/decode diagnostics (rate-limited logging)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_LOG_INTERVAL_S: float = 5.0


@dataclass
class ThumbPaintDiagnostics:
    """
    Counters for thumbnail paint and decode behavior in prime performance mode.

    Logging is rate-limited to once per :data:`_LOG_INTERVAL_S` seconds.
    """

    sync_load_attempts_blocked: int = 0
    deferred_decode_requests: int = 0
    visible_ready_hits: int = 0
    placeholder_paints: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    evictions: int = 0
    cache_items: int = 0
    cache_mb: float = 0.0
    fast_scroll_suppression_count: int = 0
    stale_epoch_drops: int = 0
    priority_decode_requests: int = 0
    directional_prefetch_count: int = 0
    bridge_jobs_suppressed: int = 0
    bridge_jobs_pending: int = 0
    bridge_jobs_running: int = 0
    bridge_duplicate_skips: int = 0
    bridge_idle_enqueues: int = 0
    native_jobs_enqueued: int = 0
    native_jobs_in_flight: int = 0
    blender_jobs_skipped_native_supported: int = 0
    blender_fallback_jobs: int = 0
    manual_blender_jobs: int = 0
    idle_repaint_cycles: int = 0
    cache_resets: int = 0
    selection_repaints: int = 0
    hover_repaints: int = 0
    layout_reflows: int = 0
    thumbnail_widget_rebuilds: int = 0
    decoration_cache_hits: int = 0

    _last_log_monotonic: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def note_sync_blocked(self) -> None:
        with self._lock:
            self.sync_load_attempts_blocked += 1

    def note_deferred_decode(self) -> None:
        with self._lock:
            self.deferred_decode_requests += 1

    def note_visible_ready(self) -> None:
        with self._lock:
            self.visible_ready_hits += 1

    def note_placeholder(self) -> None:
        with self._lock:
            self.placeholder_paints += 1

    def note_decoration_cache_hit(self) -> None:
        with self._lock:
            self.decoration_cache_hits += 1

    def note_cache_reset(self) -> None:
        with self._lock:
            self.cache_resets += 1

    def note_idle_repaint_cycle(self) -> None:
        with self._lock:
            self.idle_repaint_cycles += 1

    def note_thumbnail_widget_rebuild(self) -> None:
        with self._lock:
            self.thumbnail_widget_rebuilds += 1

    def note_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def note_cache_miss(self) -> None:
        with self._lock:
            self.cache_misses += 1

    def note_fast_scroll_suppression(self) -> None:
        with self._lock:
            self.fast_scroll_suppression_count += 1

    def note_stale_epoch_drop(self) -> None:
        with self._lock:
            self.stale_epoch_drops += 1

    def note_priority_decode_request(self) -> None:
        with self._lock:
            self.priority_decode_requests += 1

    def note_directional_prefetch(self, row_count: int) -> None:
        if row_count <= 0:
            return
        with self._lock:
            self.directional_prefetch_count += int(row_count)

    def note_bridge_suppressed(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.bridge_jobs_suppressed += int(count)

    def note_bridge_duplicate_skip(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.bridge_duplicate_skips += int(count)

    def note_bridge_idle_enqueue(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.bridge_idle_enqueues += int(count)

    def note_native_jobs_enqueued(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.native_jobs_enqueued += int(count)

    def sync_native_queue_stats(self, in_flight: int) -> None:
        """Update live native queue depth (Prime v1.0)."""
        with self._lock:
            self.native_jobs_in_flight = max(0, int(in_flight))

    def note_blender_skipped_native_supported(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.blender_jobs_skipped_native_supported += int(count)

    def note_blender_fallback_jobs(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.blender_fallback_jobs += int(count)

    def note_manual_blender_jobs(self, count: int = 1) -> None:
        if count <= 0:
            return
        with self._lock:
            self.manual_blender_jobs += int(count)

    def sync_bridge_queue_stats(self, pending: int, running: int) -> None:
        """Update live bridge queue depth counters (Prime v0.10)."""
        with self._lock:
            self.bridge_jobs_pending = max(0, int(pending))
            self.bridge_jobs_running = max(0, int(running))

    def update_cache_stats(self, stats: dict[str, object]) -> None:
        """Merge LRU footprint counters from :meth:`ThumbnailPixmapLRUCache.stats`."""
        with self._lock:
            self.cache_items = int(stats.get("cache_items", 0))
            self.cache_mb = float(stats.get("cache_mb", 0.0))
            self.evictions = int(stats.get("evictions", 0))

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "sync_load_attempts_blocked": int(self.sync_load_attempts_blocked),
                "deferred_decode_requests": int(self.deferred_decode_requests),
                "visible_ready_hits": int(self.visible_ready_hits),
                "placeholder_paints": int(self.placeholder_paints),
                "cache_hits": int(self.cache_hits),
                "cache_misses": int(self.cache_misses),
                "evictions": int(self.evictions),
                "cache_items": int(self.cache_items),
                "cache_mb": float(self.cache_mb),
                "fast_scroll_suppression_count": int(self.fast_scroll_suppression_count),
                "stale_epoch_drops": int(self.stale_epoch_drops),
                "priority_decode_requests": int(self.priority_decode_requests),
                "directional_prefetch_count": int(self.directional_prefetch_count),
                "bridge_jobs_suppressed": int(self.bridge_jobs_suppressed),
                "bridge_jobs_pending": int(self.bridge_jobs_pending),
                "bridge_jobs_running": int(self.bridge_jobs_running),
                "bridge_duplicate_skips": int(self.bridge_duplicate_skips),
                "bridge_idle_enqueues": int(self.bridge_idle_enqueues),
                "native_jobs_enqueued": int(self.native_jobs_enqueued),
                "native_jobs_in_flight": int(self.native_jobs_in_flight),
                "blender_jobs_skipped_native_supported": int(
                    self.blender_jobs_skipped_native_supported
                ),
                "blender_fallback_jobs": int(self.blender_fallback_jobs),
                "manual_blender_jobs": int(self.manual_blender_jobs),
                "idle_repaint_cycles": int(self.idle_repaint_cycles),
                "cache_resets": int(self.cache_resets),
                "selection_repaints": int(self.selection_repaints),
                "hover_repaints": int(self.hover_repaints),
                "layout_reflows": int(self.layout_reflows),
                "thumbnail_widget_rebuilds": int(self.thumbnail_widget_rebuilds),
                "decoration_cache_hits": int(self.decoration_cache_hits),
            }

    def maybe_log_summary(self) -> None:
        """Emit a debug summary at most once every five seconds."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_log_monotonic < _LOG_INTERVAL_S:
                return
            self._last_log_monotonic = now
            snap = {
                "sync_load_attempts_blocked": self.sync_load_attempts_blocked,
                "deferred_decode_requests": self.deferred_decode_requests,
                "visible_ready_hits": self.visible_ready_hits,
                "placeholder_paints": self.placeholder_paints,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "evictions": self.evictions,
                "cache_items": self.cache_items,
                "cache_mb": self.cache_mb,
                "fast_scroll_suppression_count": self.fast_scroll_suppression_count,
                "stale_epoch_drops": self.stale_epoch_drops,
                "priority_decode_requests": self.priority_decode_requests,
                "directional_prefetch_count": self.directional_prefetch_count,
                "bridge_jobs_suppressed": self.bridge_jobs_suppressed,
                "bridge_jobs_pending": self.bridge_jobs_pending,
                "bridge_jobs_running": self.bridge_jobs_running,
                "bridge_duplicate_skips": self.bridge_duplicate_skips,
                "bridge_idle_enqueues": self.bridge_idle_enqueues,
                "native_jobs_enqueued": self.native_jobs_enqueued,
                "native_jobs_in_flight": self.native_jobs_in_flight,
                "blender_jobs_skipped_native_supported": self.blender_jobs_skipped_native_supported,
                "blender_fallback_jobs": self.blender_fallback_jobs,
                "manual_blender_jobs": self.manual_blender_jobs,
                "idle_repaint_cycles": self.idle_repaint_cycles,
                "cache_resets": self.cache_resets,
                "selection_repaints": self.selection_repaints,
                "hover_repaints": self.hover_repaints,
                "layout_reflows": self.layout_reflows,
                "thumbnail_widget_rebuilds": self.thumbnail_widget_rebuilds,
                "decoration_cache_hits": self.decoration_cache_hits,
            }
        logger.info("Prime thumb paint: %s", snap)

    def reset(self) -> None:
        with self._lock:
            self.sync_load_attempts_blocked = 0
            self.deferred_decode_requests = 0
            self.visible_ready_hits = 0
            self.placeholder_paints = 0
            self.cache_hits = 0
            self.cache_misses = 0
            self.evictions = 0
            self.cache_items = 0
            self.cache_mb = 0.0
            self.fast_scroll_suppression_count = 0
            self.stale_epoch_drops = 0
            self.priority_decode_requests = 0
            self.directional_prefetch_count = 0
            self.bridge_jobs_suppressed = 0
            self.bridge_jobs_pending = 0
            self.bridge_jobs_running = 0
            self.bridge_duplicate_skips = 0
            self.bridge_idle_enqueues = 0
            self.native_jobs_enqueued = 0
            self.native_jobs_in_flight = 0
            self.blender_jobs_skipped_native_supported = 0
            self.blender_fallback_jobs = 0
            self.manual_blender_jobs = 0
            self.idle_repaint_cycles = 0
            self.cache_resets = 0
            self.selection_repaints = 0
            self.hover_repaints = 0
            self.layout_reflows = 0
            self.thumbnail_widget_rebuilds = 0
            self.decoration_cache_hits = 0
            self._last_log_monotonic = 0.0
