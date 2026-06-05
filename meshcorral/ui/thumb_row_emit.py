"""Emit ``dataChanged`` only for visible browse rows (never full-model repaint)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QModelIndex, Qt

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.file_columns import thumb_column_index, thumb_health_column_index
from meshcorral.ui.file_table_model import FileTableModel
from meshcorral.ui.gallery_list_model import GalleryListModel

_THUMB_ROLES = [
    Qt.ItemDataRole.DecorationRole,
    Qt.ItemDataRole.ToolTipRole,
    Qt.ItemDataRole.SizeHintRole,
    Qt.UserRole,
]


def row_indices_for_path_keys(
    view_records: Sequence[FileRecord],
    path_keys: frozenset[str] | set[str],
    *,
    visible_rows: Sequence[int] | None = None,
) -> list[int]:
    """
    Return row indices in *view_records* matching *path_keys*.

    When *visible_rows* is set, only matching rows in that set are returned.
    """
    if not path_keys or not view_records:
        return []
    want = set(path_keys)
    visible_set = set(visible_rows) if visible_rows is not None else None
    out: list[int] = []
    for row, record in enumerate(view_records):
        if visible_set is not None and row not in visible_set:
            continue
        if _norm_path_key(record.path) in want:
            out.append(row)
    return out


def _contiguous_ranges(sorted_rows: list[int]) -> list[tuple[int, int]]:
    if not sorted_rows:
        return []
    ranges: list[tuple[int, int]] = []
    start = prev = sorted_rows[0]
    for row in sorted_rows[1:]:
        if row == prev + 1:
            prev = row
            continue
        ranges.append((start, prev))
        start = prev = row
    ranges.append((start, prev))
    return ranges


def emit_table_thumb_rows_at_indices(model: FileTableModel, row_indices: Sequence[int]) -> None:
    """``dataChanged`` for thumb + health columns on specific table rows only."""
    if not row_indices:
        return
    col_thumb = thumb_column_index()
    col_health = thumb_health_column_index()
    c_lo = min(col_thumb, col_health)
    c_hi = max(col_thumb, col_health)
    for start, end in _contiguous_ranges(sorted(set(int(r) for r in row_indices))):
        i1 = model.index(start, c_lo)
        i2 = model.index(end, c_hi)
        model.dataChanged.emit(i1, i2, _THUMB_ROLES)


def emit_gallery_rows_at_indices(model: GalleryListModel, row_indices: Sequence[int]) -> None:
    """``dataChanged`` for gallery decoration on specific rows only."""
    if not row_indices:
        return
    roles = [
        Qt.ItemDataRole.DecorationRole,
        Qt.ItemDataRole.SizeHintRole,
        Qt.ItemDataRole.ToolTipRole,
    ]
    for start, end in _contiguous_ranges(sorted(set(int(r) for r in row_indices))):
        i1 = model.index(start)
        i2 = model.index(end)
        model.dataChanged.emit(i1, i2, roles)


def emit_visible_thumb_refresh(
    *,
    view_records: Sequence[FileRecord],
    path_keys: frozenset[str] | set[str],
    visible_row_indices: Sequence[int],
    table_model: FileTableModel,
    gallery_model: GalleryListModel,
) -> list[FileRecord]:
    """
    Refresh only visible rows whose path keys are in *path_keys*.

    Returns the :class:`FileRecord` rows that were refreshed (for lazy health resolve).
    """
    rows = row_indices_for_path_keys(
        view_records,
        path_keys,
        visible_rows=visible_row_indices,
    )
    if not rows:
        return []
    emit_table_thumb_rows_at_indices(table_model, rows)
    emit_gallery_rows_at_indices(gallery_model, rows)
    return [view_records[r] for r in rows]
