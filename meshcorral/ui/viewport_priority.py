"""Viewport row priority and direction-aware prefetch (Prime Performance Pass v0.9)."""

from __future__ import annotations

from collections.abc import Sequence

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.scroll_velocity import ScrollDirection

# Fraction of visible row span to preload ahead/behind the viewport.
PREFETCH_FORWARD_SCREEN_LOCAL: float = 2.0
PREFETCH_BACKWARD_SCREEN_LOCAL: float = 0.5
PREFETCH_FORWARD_SCREEN_REMOTE: float = 1.0
PREFETCH_BACKWARD_SCREEN_REMOTE: float = 0.25


def visible_row_span(visible_row_indices: Sequence[int]) -> int:
    """Approximate visible row count from first/last visible indices."""
    if not visible_row_indices:
        return 0
    return max(1, int(max(visible_row_indices) - min(visible_row_indices) + 1))


def directional_prefetch_row_indices(
    visible_row_indices: Sequence[int],
    total_rows: int,
    *,
    direction: ScrollDirection,
    network_like: bool,
) -> list[int]:
    """
    Expand visible rows with direction-aware preload margins.

    Scrolling down preloads more rows below; scrolling up preloads more above.
    """
    if total_rows <= 0:
        return []
    visible = sorted({int(r) for r in visible_row_indices if 0 <= int(r) < total_rows})
    if not visible:
        return []

    span = visible_row_span(visible)
    if network_like:
        forward_frac = PREFETCH_FORWARD_SCREEN_REMOTE
        backward_frac = PREFETCH_BACKWARD_SCREEN_REMOTE
    else:
        forward_frac = PREFETCH_FORWARD_SCREEN_LOCAL
        backward_frac = PREFETCH_BACKWARD_SCREEN_LOCAL

    forward_rows = max(0, int(span * forward_frac))
    backward_rows = max(0, int(span * backward_frac))

    top = min(visible)
    bottom = max(visible)

    if direction == "down":
        low = max(0, top - int(backward_rows))
        high = min(total_rows - 1, bottom + int(forward_rows))
    elif direction == "up":
        low = max(0, top - int(forward_rows))
        high = min(total_rows - 1, bottom + int(backward_rows))
    else:
        margin = max(forward_rows, backward_rows)
        low = max(0, top - margin)
        high = min(total_rows - 1, bottom + margin)

    ordered: list[int] = []
    seen: set[int] = set()

    def _add(row: int) -> None:
        if 0 <= row < total_rows and row not in seen:
            seen.add(row)
            ordered.append(row)

    for row in visible:
        _add(row)
    if direction == "down":
        for row in range(bottom + 1, high + 1):
            _add(row)
        for row in range(top - 1, low - 1, -1):
            _add(row)
    elif direction == "up":
        for row in range(top - 1, low - 1, -1):
            _add(row)
        for row in range(bottom + 1, high + 1):
            _add(row)
    else:
        for row in range(top - 1, low - 1, -1):
            _add(row)
        for row in range(bottom + 1, high + 1):
            _add(row)

    return ordered


def prioritize_viewport_records(
    view_records: Sequence[FileRecord],
    row_indices: Sequence[int],
    *,
    selected_row: int | None = None,
) -> list[FileRecord]:
    """
    Order records for viewport work: selected, visible, then preload rows.

    *row_indices* should already reflect directional prefetch expansion.
    """
    n = len(view_records)
    if n <= 0:
        return []

    ordered_rows: list[int] = []
    seen_rows: set[int] = set()

    def _add_row(row: int) -> None:
        if 0 <= row < n and row not in seen_rows:
            seen_rows.add(row)
            ordered_rows.append(row)

    if selected_row is not None:
        _add_row(int(selected_row))

    for row in row_indices:
        _add_row(int(row))

    out: list[FileRecord] = []
    seen_keys: set[str] = set()
    for row in ordered_rows:
        record = view_records[row]
        key = _norm_path_key(record.path)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(record)
    return out
