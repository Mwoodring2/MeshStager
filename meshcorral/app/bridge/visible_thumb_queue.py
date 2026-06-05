"""Visible-first ordering for thumbnail auto-queue (Prime Performance Pass)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from meshcorral.app.bridge.auto_thumb_scan import is_auto_thumbnail_extension
from meshcorral.app.config import SUPPORTED_IMAGE_EXTENSIONS
from meshcorral.models.file_record import FileRecord

# Rows above/below the viewport to prefer when preloading thumbnails.
DEFAULT_VISIBLE_MARGIN: int = 3


def expand_row_indices(
    row_indices: Sequence[int],
    total_rows: int,
    margin: int = DEFAULT_VISIBLE_MARGIN,
) -> list[int]:
    """
    Expand *row_indices* by *margin* rows above and below, clamped to ``[0, total_rows)``.

    Preserves first-seen order: visible rows first, then margin neighbors.
    """
    if total_rows <= 0:
        return []
    margin = max(0, int(margin))
    seen: set[int] = set()
    ordered: list[int] = []

    def _add(row: int) -> None:
        if 0 <= row < total_rows and row not in seen:
            seen.add(row)
            ordered.append(row)

    for row in row_indices:
        if row < 0 or row >= total_rows:
            continue
        _add(int(row))
        for delta in range(1, margin + 1):
            _add(int(row) - delta)
            _add(int(row) + delta)
    return ordered


def records_at_rows(view_records: Sequence[FileRecord], row_indices: Sequence[int]) -> list[FileRecord]:
    """Map row indices into :class:`FileRecord` rows (skips out-of-range)."""
    out: list[FileRecord] = []
    n = len(view_records)
    for row in row_indices:
        if 0 <= row < n:
            out.append(view_records[row])
    return out


def prioritize_visible_records(
    view_records: Sequence[FileRecord],
    visible_row_indices: Sequence[int],
    *,
    margin: int = DEFAULT_VISIBLE_MARGIN,
) -> list[FileRecord]:
    """
    Return view records ordered visible-first, then margin neighbors.

    Does not include rows outside the expanded viewport window.
    """
    rows = expand_row_indices(visible_row_indices, len(view_records), margin=margin)
    return records_at_rows(view_records, rows)


def select_auto_thumbnail_candidates(
    ordered_records: Sequence[FileRecord],
    *,
    has_thumbnail: Callable[[FileRecord], bool],
    cap: int,
    unlimited_cap: int,
) -> list[FileRecord]:
    """
    From *ordered_records*, return mesh types missing thumbnails up to *cap*.

    *cap* of *unlimited_cap* means no limit.
    """
    missing: list[FileRecord] = []
    for record in ordered_records:
        if not is_auto_thumbnail_extension(record):
            continue
        if has_thumbnail(record):
            continue
        missing.append(record)
        if cap != unlimited_cap and len(missing) >= cap:
            break
    return missing


def is_raster_thumbnail_extension(record: FileRecord) -> bool:
    """True when *record* is a supported raster thumbnail source (png, jpg, psd, …)."""
    ext = (record.extension or record.path.suffix).lower().strip()
    return ext in SUPPORTED_IMAGE_EXTENSIONS


def select_raster_decode_candidates(
    ordered_records: Sequence[FileRecord],
    *,
    is_ready: Callable[[FileRecord], bool],
    cap: int,
    unlimited_cap: int,
) -> list[FileRecord]:
    """
    From *ordered_records*, return raster types not yet READY, up to *cap*.

    Used for visible-first READY priming on image folders (no decode on scan).
    """
    missing: list[FileRecord] = []
    for record in ordered_records:
        if not is_raster_thumbnail_extension(record):
            continue
        if is_ready(record):
            continue
        missing.append(record)
        if cap != unlimited_cap and len(missing) >= cap:
            break
    return missing


def merge_visible_first(
    primary: Sequence[FileRecord],
    secondary: Sequence[FileRecord],
) -> list[FileRecord]:
    """Concatenate *primary* then *secondary*, de-duplicated by resolved path key."""
    from meshcorral.app.bridge.thumb_index import _norm_path_key

    seen: set[str] = set()
    out: list[FileRecord] = []
    for record in list(primary) + list(secondary):
        key = _norm_path_key(record.path)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out
