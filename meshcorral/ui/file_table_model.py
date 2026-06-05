"""Qt table model for file records."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, TYPE_CHECKING

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSize

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.file_columns import (
    FILE_COLUMNS,
    THUMB_COLUMN_KEY,
    THUMB_HEALTH_COLUMN_KEY,
    thumb_column_index,
    thumb_health_column_index,
)

if TYPE_CHECKING:
    from meshcorral.ui.thumbnail_controller import ThumbnailViewController

logger = logging.getLogger(__name__)
_TIMING_LOGS: bool = os.environ.get("ROUNDUP_TIMING", "").strip() == "1"

class FileTableModel(QAbstractTableModel):
    """Table model for ``FileRecord`` rows; layout comes from ``FILE_COLUMNS``."""

    def __init__(self) -> None:
        super().__init__()
        self._records: list[FileRecord] = []
        self._thumb_controller: ThumbnailViewController | None = None

    def set_thumbnail_controller(self, controller: ThumbnailViewController | None) -> None:
        """Connect optional Blender thumbnail display (icon column, lazy load)."""
        self._thumb_controller = controller
        if controller is not None:
            controller.set_model(self)

    def set_records(self, records: list[FileRecord]) -> None:
        """Replace all rows in the model."""
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()

    def set_rows(self, rows: list[FileRecord]) -> None:
        """Replace all rows (same as :meth:`set_records`, kept for callers)."""
        self.set_records(rows)

    def append_records(self, rows: list[FileRecord]) -> None:
        """Append rows (used during staged folder scan). Prefer :meth:`set_rows` once when done."""
        if not rows:
            return
        n = len(self._records)
        self.beginInsertRows(QModelIndex(), n, n + len(rows) - 1)
        self._records.extend(rows)
        self.endInsertRows()

    def column_key(self, column_index: int) -> str:
        """Stable column id for context menus, exports, etc."""
        return FILE_COLUMNS[column_index].key

    def column_header(self, column_index: int) -> str:
        """Header label for the given column index."""
        return FILE_COLUMNS[column_index].header

    def record_at(self, row: int) -> FileRecord | None:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(self._records)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(FILE_COLUMNS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(FILE_COLUMNS):
                return FILE_COLUMNS[section].header
            return None
        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None
        if not (0 <= index.row() < len(self._records)):
            return None
        if not (0 <= index.column() < len(FILE_COLUMNS)):
            return None

        record = self._records[index.row()]
        column = FILE_COLUMNS[index.column()]
        value = column.value_getter(record)

        if column.key == THUMB_HEALTH_COLUMN_KEY and self._thumb_controller is not None:
            if role == Qt.DecorationRole:
                icon = self._thumb_controller.health_badge_icon(record)
                return icon if icon is not None and not icon.isNull() else None
            if role == Qt.ToolTipRole:
                return self._thumb_controller.health_tooltip(record)
            if role == Qt.SizeHintRole:
                from meshcorral.ui.thumbnails.badge_styles import BADGE_SIZE_MEDIUM

                side = BADGE_SIZE_MEDIUM + 6
                return QSize(side, side)
            if role == Qt.DisplayRole:
                return ""
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignHCenter | Qt.AlignVCenter)
            if role == Qt.UserRole:
                return self._thumb_controller.thumb_health(record).sort_value
            return None

        if column.key == THUMB_COLUMN_KEY and self._thumb_controller is not None:
            if role == Qt.DecorationRole:
                d = self._thumb_controller.table_decoration_for(record)
                return d if d is not None and not d.isNull() else None
            if role == Qt.SizeHintRole:
                return self._thumb_controller.table_thumb_size_hint()
            if role == Qt.DisplayRole:
                return ""
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignHCenter | Qt.AlignVCenter)
            if role == Qt.UserRole:
                if column.sort_getter is not None:
                    return column.sort_getter(record)
                return value
            return None

        if role == Qt.DisplayRole:
            if column.display_formatter is not None:
                return column.display_formatter(value)
            return "" if value is None else str(value)

        if role == Qt.UserRole:
            if column.sort_getter is not None:
                return column.sort_getter(record)
            return value

        if role == Qt.TextAlignmentRole:
            if column.key == "size_bytes":
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        if role == Qt.ToolTipRole and column.key == "name":
            return record.name

        return None

    def emit_thumb_rows_for_path_key(self, path_key: str) -> None:
        """Re-decorate the thumbnail for every visible row that matches *path_key* (resolved path)."""
        col_thumb = thumb_column_index()
        col_health = thumb_health_column_index()
        c_lo = min(col_thumb, col_health)
        c_hi = max(col_thumb, col_health)
        roles = [
            Qt.DecorationRole,
            Qt.ToolTipRole,
            Qt.SizeHintRole,
            Qt.UserRole,
        ]
        for row, rec in enumerate(self._records):
            if _norm_path_key(rec.path) == path_key:
                i1 = self.index(row, c_lo)
                i2 = self.index(row, c_hi)
                self.dataChanged.emit(i1, i2, roles)

    def emit_all_thumb_rows(self) -> None:
        """Notify that every row's thumbnail may have changed (after index refresh)."""
        if not self._records:
            return
        t0 = time.perf_counter()
        col_thumb = thumb_column_index()
        col_health = thumb_health_column_index()
        c_lo = min(col_thumb, col_health)
        c_hi = max(col_thumb, col_health)
        r1 = self.index(0, c_lo)
        r2 = self.index(len(self._records) - 1, c_hi)
        self.dataChanged.emit(
            r1,
            r2,
            [Qt.DecorationRole, Qt.ToolTipRole, Qt.SizeHintRole, Qt.UserRole],
        )
        if _TIMING_LOGS:
            logger.info(
                "TIMING emit_all_thumb_rows: %.2fms rows=%s",
                (time.perf_counter() - t0) * 1000.0,
                len(self._records),
            )

    def apply_metadata_batch(self, updates: dict[str, tuple[int | None, float | None]]) -> int:
        """
        Patch ``size_bytes`` and ``modified_time`` on visible rows from background stat.

        *updates* maps :func:`_norm_path_key` → ``(size_bytes, modified_time)``. Emits
        ``dataChanged`` only over the contiguous metadata columns of touched rows.

        Returns the number of rows updated.
        """
        if not updates or not self._records:
            return 0
        size_col_idx = -1
        mtime_col_idx = -1
        for idx, col in enumerate(FILE_COLUMNS):
            if col.key == "size_bytes":
                size_col_idx = idx
            elif col.key == "modified_time":
                mtime_col_idx = idx
        if size_col_idx < 0 or mtime_col_idx < 0:
            return 0
        c_lo = min(size_col_idx, mtime_col_idx)
        c_hi = max(size_col_idx, mtime_col_idx)
        roles = [Qt.DisplayRole, Qt.UserRole]
        touched = 0
        for row, rec in enumerate(self._records):
            patch = updates.get(_norm_path_key(rec.path))
            if patch is None:
                continue
            size_bytes, modified_time = patch
            if rec.size_bytes == size_bytes and rec.modified_time == modified_time:
                continue
            self._records[row] = rec.with_metadata(
                size_bytes=size_bytes, modified_time=modified_time
            )
            i1 = self.index(row, c_lo)
            i2 = self.index(row, c_hi)
            self.dataChanged.emit(i1, i2, roles)
            touched += 1
        return touched

    def emit_thumb_column_metrics_changed(self) -> None:
        """Re-run decoration and row sizing after a global thumb pixel size change."""
        if not self._records:
            return
        col = thumb_column_index()
        r1 = self.index(0, col)
        r2 = self.index(len(self._records) - 1, col)
        self.dataChanged.emit(r1, r2, [Qt.DecorationRole, Qt.SizeHintRole])

    def records(self) -> list[FileRecord]:
        """Return a copy of the current rows (the current view)."""
        return list(self._records)
