"""Visible row helpers for table and gallery browse views."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint
from PySide6.QtWidgets import QListView, QTableView


def _rows_from_index_range(top: int, bottom: int) -> list[int]:
    if bottom < top:
        top, bottom = bottom, top
    if top < 0:
        return []
    return list(range(top, bottom + 1))


def visible_row_indices_table(table: QTableView) -> list[int]:
    """Row indices currently visible in a :class:`QTableView` viewport."""
    model = table.model()
    if model is None or model.rowCount() <= 0:
        return []
    vp = table.viewport()
    top_left = table.indexAt(vp.rect().topLeft())
    bottom_left = table.indexAt(
        QPoint(vp.rect().left(), max(vp.rect().top(), vp.rect().bottom() - 2))
    )
    top = top_left.row() if top_left.isValid() else 0
    bottom = bottom_left.row() if bottom_left.isValid() else model.rowCount() - 1
    return _rows_from_index_range(top, bottom)


def visible_row_indices_gallery(gallery: QListView) -> list[int]:
    """Row indices currently visible in icon-mode :class:`QListView`."""
    model = gallery.model()
    if model is None or model.rowCount() <= 0:
        return []
    vp = gallery.viewport()
    top_left = gallery.indexAt(vp.rect().topLeft())
    bottom_right = gallery.indexAt(
        QPoint(vp.rect().right() - 2, max(vp.rect().top(), vp.rect().bottom() - 2))
    )
    top = top_left.row() if top_left.isValid() else 0
    bottom = bottom_right.row() if bottom_right.isValid() else model.rowCount() - 1
    return _rows_from_index_range(top, bottom)


def visible_row_indices_for_browse_widget(
    *,
    view_stack_index: int,
    table: QTableView,
    gallery: QListView,
) -> list[int]:
    """Return visible rows for the active browse widget (0=table, 1=gallery)."""
    if view_stack_index == 0:
        return visible_row_indices_table(table)
    return visible_row_indices_gallery(gallery)
