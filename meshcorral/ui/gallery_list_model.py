"""
List model for the gallery (icon) view: same :class:`FileRecord` rows as the table, no copy.

Uses :class:`QAbstractListModel` behind :class:`QListView` icon mode with uniform item sizes.
Scaled pixmaps and paint are handled in :class:`~meshcorral.ui.gallery_item_delegate.GalleryItemDelegate`
and :meth:`~meshcorral.ui.thumbnail_controller.ThumbnailViewController.gallery_paint_pixmap`.

TODO(RC3+): optional async icon provider / background loader for off-thread scaling; keep
virtualized QListView rather than QWidget-per-thumbnail.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSize

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.filename_display import filename_tooltip, truncate_filename
from meshcorral.ui.ui_scroll_profiler import UiScrollProfiler
from meshcorral.utils.filesize_display import format_file_size_display

if TYPE_CHECKING:
    from meshcorral.ui.thumbnail_controller import ThumbnailViewController

logger = logging.getLogger(__name__)
_TIMING_LOGS: bool = os.environ.get("ROUNDUP_TIMING", "").strip() == "1"

# Whole FileRecord for delegate and double-click (PySide6 passes Python objects).
GALLERY_RECORD_ROLE: int = Qt.UserRole + 20


class GalleryListModel(QAbstractListModel):
    """
    One row per visible :class:`FileRecord`; :meth:`set_records` mirrors the filtered table list.
    """

    def __init__(self, thumb: "ThumbnailViewController", parent: Any = None) -> None:
        super().__init__(parent)
        self._thumb = thumb
        self._records: list[FileRecord] = []
        self._layout_generation: int = 0

    @property
    def layout_generation(self) -> int:
        """Increments only on full model replace (:meth:`set_records`), not on scroll."""
        return int(self._layout_generation)

    def set_records(self, records: list[FileRecord]) -> None:
        """Replace rows (call with the same list as :class:`~meshcorral.ui.file_table_model.FileTableModel`)."""
        t0 = time.perf_counter()
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()
        self._layout_generation += 1
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        UiScrollProfiler.note_layout_rebuild_ms(elapsed_ms)
        if UiScrollProfiler.file_logging_enabled():
            UiScrollProfiler.log_layout_rebuild(
                elapsed_ms=elapsed_ms,
                total_gallery_item_count=len(self._records),
                reason="set_records",
            )

    def append_records(self, rows: list[FileRecord]) -> None:
        """Append rows (staged scan). Prefer :meth:`set_records` for a single full replace."""
        if not rows:
            return
        n = len(self._records)
        self.beginInsertRows(QModelIndex(), n, n + len(rows) - 1)
        self._records.extend(rows)
        self.endInsertRows()

    def record_at(self, row: int) -> FileRecord | None:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(self._records)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid() or not (0 <= index.row() < len(self._records)):
            return None
        record = self._records[index.row()]
        if role == GALLERY_RECORD_ROLE:
            return record
        if role == Qt.ItemDataRole.DecorationRole:
            # GalleryItemDelegate paints via :meth:`ThumbnailViewController.gallery_paint_pixmap`
            # so QListView does not decode/scale icons on every scroll repaint.
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return truncate_filename(record.name)
        if role == Qt.ItemDataRole.SizeHintRole:
            return self._cell_size()
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = self._thumb.health_tooltip(record)
            return filename_tooltip(record.name, extra_lines=tip or str(record.path))
        return None

    def _cell_size(self) -> QSize:
        px = self._thumb.display_pixel_size()
        text_h = 18 + 16 + 16
        w = max(px + 40, 168)
        h = px + 12 + text_h + 8
        return QSize(w, h)

    def current_cell_size(self) -> QSize:
        """Uniform item size for :class:`QListView` in icon mode (depends on zoom)."""
        return self._cell_size()

    def emit_items_for_path_key(self, path_key: str) -> None:
        """Re-decorate the card(s) for a normalized source path key."""
        for row, rec in enumerate(self._records):
            if _norm_path_key(rec.path) == path_key:
                i1 = self.index(row)
                self.dataChanged.emit(
                    i1,
                    i1,
                    [
                        Qt.ItemDataRole.DecorationRole,
                        Qt.ItemDataRole.SizeHintRole,
                        Qt.ItemDataRole.ToolTipRole,
                    ],
                )

    def apply_metadata_batch(self, updates: dict[str, tuple[int | None, float | None]]) -> int:
        """
        Patch ``size_bytes`` / ``modified_time`` on gallery rows from background stat.

        Emits one ``dataChanged`` per updated row over :class:`Qt.ItemDataRole.ToolTipRole`
        (the only gallery role that surfaces size). Returns the number of rows updated.
        """
        if not updates or not self._records:
            return 0
        touched = 0
        roles = [Qt.ItemDataRole.ToolTipRole]
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
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, roles)
            touched += 1
        return touched

    def emit_all_item_metrics(self) -> None:
        """Notify that decoration size and cell size may have changed (e.g. pixel size slider)."""
        if not self._records:
            return
        t0 = time.perf_counter()
        r1 = self.index(0)
        r2 = self.index(len(self._records) - 1)
        self.dataChanged.emit(
            r1,
            r2,
            [
                Qt.ItemDataRole.DecorationRole,
                Qt.ItemDataRole.SizeHintRole,
                Qt.ItemDataRole.ToolTipRole,
            ],
        )
        if _TIMING_LOGS:
            logger.info(
                "TIMING emit_all_item_metrics: %.2fms rows=%s",
                (time.perf_counter() - t0) * 1000.0,
                len(self._records),
            )
