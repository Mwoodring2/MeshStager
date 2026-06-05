"""Prime v0.10 — Blender Bridge backpressure caps and viewport tier ordering."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from meshcorral.app.bridge.auto_thumb_scan import is_auto_thumbnail_extension
from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord

# Hard cap on pending + running bridge jobs (Prime v0.10).
MAX_PENDING_BRIDGE_JOBS_LOCAL: int = 32
MAX_PENDING_BRIDGE_JOBS_REMOTE: int = 12

# UI must be idle this long before idle-tier background bridge fill (seconds).
BRIDGE_IDLE_BACKGROUND_MIN_S: float = 2.0

BridgeJobTier = Literal["selected", "visible", "directional_preload", "idle_background"]

TIER_ORDER: tuple[BridgeJobTier, ...] = (
    "selected",
    "visible",
    "directional_preload",
    "idle_background",
)


class BridgeEnqueueReject(str, Enum):
    """Reason an enqueue attempt was rejected."""

    OK = ""
    DUPLICATE = "duplicate"
    CAP = "cap"
    SHUTDOWN = "shutdown"
    NO_BLENDER = "no_blender"
    IO_ERROR = "io_error"
    NOT_ROUTED = "not_routed"


def max_pending_bridge_jobs(*, network_like: bool) -> int:
    """Return the pending+running cap for local vs remote-like folders."""
    if network_like:
        return MAX_PENDING_BRIDGE_JOBS_REMOTE
    return MAX_PENDING_BRIDGE_JOBS_LOCAL


def bridge_load_count(*, pending: int, running: int) -> int:
    """Combined in-flight bridge jobs (pending queue + active Blender run)."""
    return max(0, int(pending)) + max(0, int(running))


@dataclass(frozen=True, slots=True)
class BridgeEnqueueStats:
    """Summary of one tiered enqueue pass."""

    enqueued: int = 0
    suppressed_cap: int = 0
    duplicate_skips: int = 0
    idle_tier_enqueued: int = 0


def bridge_records_by_tier(
    view_records: Sequence[FileRecord],
    *,
    visible_row_indices: Sequence[int],
    prefetch_row_indices: Sequence[int],
    selected_row: int | None,
    idle_background_row_indices: Sequence[int] | None = None,
) -> dict[BridgeJobTier, list[FileRecord]]:
    """
    Split *view_records* into bridge priority tiers.

    Rows are classified as selected, visible, directional preload, or idle background.
    """
    n = len(view_records)
    if n <= 0:
        return {tier: [] for tier in TIER_ORDER}

    visible_set = {int(r) for r in visible_row_indices if 0 <= int(r) < n}
    prefetch_set = {int(r) for r in prefetch_row_indices if 0 <= int(r) < n}
    idle_rows = (
        [int(r) for r in idle_background_row_indices if 0 <= int(r) < n]
        if idle_background_row_indices is not None
        else []
    )

    selected_rows: list[int] = []
    if selected_row is not None and 0 <= int(selected_row) < n:
        selected_rows.append(int(selected_row))

    visible_only: list[int] = []
    for row in sorted(visible_set):
        if row not in selected_rows:
            visible_only.append(row)

    preload_only: list[int] = []
    for row in prefetch_row_indices:
        r = int(row)
        if 0 <= r < n and r not in visible_set and r not in selected_rows:
            if r not in preload_only:
                preload_only.append(r)

    idle_only: list[int] = []
    seen_idle: set[int] = set()
    for row in idle_rows:
        if row in visible_set or row in selected_rows or row in prefetch_set:
            continue
        if row not in seen_idle:
            seen_idle.add(row)
            idle_only.append(row)

    def _records_for_rows(rows: Sequence[int]) -> list[FileRecord]:
        out: list[FileRecord] = []
        seen_keys: set[str] = set()
        for row in rows:
            if not (0 <= row < n):
                continue
            record = view_records[row]
            if not is_auto_thumbnail_extension(record):
                continue
            key = _norm_path_key(record.path)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append(record)
        return out

    return {
        "selected": _records_for_rows(selected_rows),
        "visible": _records_for_rows(visible_only),
        "directional_preload": _records_for_rows(preload_only),
        "idle_background": _records_for_rows(idle_only),
    }


def idle_background_row_indices(
    view_records: Sequence[FileRecord],
    *,
    visible_row_indices: Sequence[int],
    prefetch_row_indices: Sequence[int],
    selected_row: int | None,
) -> list[int]:
    """
    Row indices eligible for idle-tier bridge fill (filtered view, not viewport tiers).

    Returns mesh-capable rows in *view_records* outside selected/visible/prefetch.
    """
    n = len(view_records)
    if n <= 0:
        return []
    tiers = bridge_records_by_tier(
        view_records,
        visible_row_indices=visible_row_indices,
        prefetch_row_indices=prefetch_row_indices,
        selected_row=selected_row,
        idle_background_row_indices=list(range(n)),
    )
    rows: list[int] = []
    seen: set[int] = set()
    for record in tiers["idle_background"]:
        try:
            row = view_records.index(record)
        except ValueError:
            continue
        if row not in seen:
            seen.add(row)
            rows.append(row)
    return rows


def enqueue_tiered_bridge_thumbnails(
    try_enqueue: Callable[..., tuple[bool, str, BridgeEnqueueReject]],
    tiers: Mapping[BridgeJobTier, Sequence[FileRecord]],
    *,
    has_thumbnail: Callable[[FileRecord], bool],
    tier_order: Sequence[BridgeJobTier] = TIER_ORDER,
    include_idle_tier: bool = False,
) -> BridgeEnqueueStats:
    """
    Enqueue missing mesh thumbnails in priority tier order.

    *try_enqueue* must return ``(ok, message, reject)`` and enforce cap/duplicate rules.
    """
    enqueued = 0
    suppressed_cap = 0
    duplicate_skips = 0
    idle_tier_enqueued = 0

    for tier in tier_order:
        if tier == "idle_background" and not include_idle_tier:
            continue
        for record in tiers.get(tier, ()):
            if has_thumbnail(record):
                continue
            ok, _msg, reject = try_enqueue(record)
            if ok:
                enqueued += 1
                if tier == "idle_background":
                    idle_tier_enqueued += 1
                continue
            if reject == BridgeEnqueueReject.CAP:
                suppressed_cap += 1
                return BridgeEnqueueStats(
                    enqueued=enqueued,
                    suppressed_cap=suppressed_cap,
                    duplicate_skips=duplicate_skips,
                    idle_tier_enqueued=idle_tier_enqueued,
                )
            if reject == BridgeEnqueueReject.DUPLICATE:
                duplicate_skips += 1
    return BridgeEnqueueStats(
        enqueued=enqueued,
        suppressed_cap=suppressed_cap,
        duplicate_skips=duplicate_skips,
        idle_tier_enqueued=idle_tier_enqueued,
    )


def bridge_idle_fill_allowed(
    *,
    scroll_idle_ms: float,
    scroll_settle_ms: int,
    decode_inflight: int,
    ui_idle_ms: float,
    min_ui_idle_ms: float = BRIDGE_IDLE_BACKGROUND_MIN_S * 1000.0,
) -> bool:
    """
    True when idle-tier background bridge generation may run.

    Requires scroll settle, no in-flight decodes, and UI idle for at least *min_ui_idle_ms*.
    """
    if decode_inflight > 0:
        return False
    if scroll_idle_ms < float(scroll_settle_ms):
        return False
    return ui_idle_ms >= float(min_ui_idle_ms)
