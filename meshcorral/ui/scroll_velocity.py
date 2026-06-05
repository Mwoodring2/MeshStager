"""Scroll velocity tracking for Prime Performance Pass v0.9."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

ScrollDirection = Literal["up", "down", "idle"]

# Pixels per second above which scrolling is considered "fast".
FAST_SCROLL_PX_PER_SECOND_LOCAL: float = 1800.0
FAST_SCROLL_PX_PER_SECOND_REMOTE: float = 900.0

# Milliseconds of idle scroll before resuming thumbnail/decode work.
SCROLL_SETTLE_MS_LOCAL: int = 160
SCROLL_SETTLE_MS_REMOTE: int = 300


@dataclass(frozen=True, slots=True)
class ScrollVelocityState:
    """Snapshot from :meth:`ScrollVelocityTracker.update`."""

    value: int
    px_per_second: float
    rows_per_second: float
    is_fast_scrolling: bool
    direction: ScrollDirection
    time_since_scroll_ms: int
    network_like: bool


class ScrollVelocityTracker:
    """
    Track browse scrollbar movement to detect fast scrolling.

    Uses scrollbar delta over elapsed wall time (approximate px/sec). Optional
    *row_height_px* converts speed into rows/sec for diagnostics.
    """

    def __init__(
        self,
        *,
        network_like: bool = False,
        row_height_px: int = 24,
    ) -> None:
        self._network_like = bool(network_like)
        self._row_height_px = max(1, int(row_height_px))
        self._last_value: int | None = None
        self._last_monotonic: float | None = None
        self._direction: ScrollDirection = "idle"
        self._last_state: ScrollVelocityState | None = None

    def set_network_like(self, network_like: bool) -> None:
        """Update remote vs local fast-scroll thresholds."""
        self._network_like = bool(network_like)

    def set_row_height_px(self, row_height_px: int) -> None:
        """Update approximate row height used for rows-per-second estimates."""
        self._row_height_px = max(1, int(row_height_px))

    def fast_scroll_threshold_px_per_second(self) -> float:
        """Return the px/sec threshold for the current network profile."""
        if self._network_like:
            return FAST_SCROLL_PX_PER_SECOND_REMOTE
        return FAST_SCROLL_PX_PER_SECOND_LOCAL

    def settle_delay_ms(self) -> int:
        """Return the post-scroll settle delay for the current network profile."""
        if self._network_like:
            return SCROLL_SETTLE_MS_REMOTE
        return SCROLL_SETTLE_MS_LOCAL

    def update(
        self,
        value: int,
        timestamp: float | None = None,
        *,
        network_like: bool | None = None,
    ) -> ScrollVelocityState:
        """
        Record a new scrollbar *value* and return the derived velocity state.

        *timestamp* defaults to :func:`time.monotonic`.
        """
        if network_like is not None:
            self._network_like = bool(network_like)
        now = float(time.monotonic() if timestamp is None else timestamp)
        ivalue = int(value)
        px_per_second = 0.0
        rows_per_second = 0.0
        direction: ScrollDirection = "idle"

        if self._last_value is not None and self._last_monotonic is not None:
            delta_v = ivalue - int(self._last_value)
            delta_t = now - float(self._last_monotonic)
            if delta_t > 0.0:
                px_per_second = abs(float(delta_v)) / delta_t
                rows_per_second = px_per_second / float(self._row_height_px)
            if delta_v > 0:
                direction = "down"
            elif delta_v < 0:
                direction = "up"

        threshold = self.fast_scroll_threshold_px_per_second()
        is_fast = px_per_second >= threshold
        if direction != "idle":
            self._direction = direction

        elapsed_ms = 0
        if self._last_monotonic is not None:
            elapsed_ms = max(0, int((now - float(self._last_monotonic)) * 1000.0))

        self._last_value = ivalue
        self._last_monotonic = now

        state = ScrollVelocityState(
            value=ivalue,
            px_per_second=px_per_second,
            rows_per_second=rows_per_second,
            is_fast_scrolling=is_fast,
            direction=self._direction,
            time_since_scroll_ms=elapsed_ms,
            network_like=self._network_like,
        )
        self._last_state = state
        return state

    def is_fast_scrolling(self) -> bool:
        """Return True when the last :meth:`update` reported fast scrolling."""
        if self._last_state is None:
            return False
        return bool(self._last_state.is_fast_scrolling)

    def direction(self) -> ScrollDirection:
        """Last scroll direction (``up`` / ``down`` / ``idle``)."""
        return self._direction

    def time_since_scroll_ms(self) -> int:
        """Milliseconds since the last :meth:`update` call."""
        if self._last_monotonic is None:
            return 0
        return max(0, int((time.monotonic() - float(self._last_monotonic)) * 1000.0))

    def last_state(self) -> ScrollVelocityState | None:
        """Most recent state snapshot, if any."""
        return self._last_state
