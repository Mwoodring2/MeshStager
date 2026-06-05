"""Event filter: profile gallery wheel events without rebuilding the model."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QListView

from meshcorral.ui.browse_viewport import visible_row_indices_gallery
from meshcorral.ui.gallery_perf_constants import gallery_max_visible_build
from meshcorral.ui.ui_scroll_profiler import UiScrollProfiler

if TYPE_CHECKING:
    from meshcorral.ui.gallery_list_model import GalleryListModel


class GalleryScrollEventFilter(QObject):
    """
    Log wheel timing and visible/total counts after Qt handles scrolling.

    Does not rebuild gallery rows or load images; profiling only.
    """

    def __init__(self, gallery: QListView, model: "GalleryListModel") -> None:
        super().__init__(gallery)
        self._gallery = gallery
        self._model = model

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.Wheel:
            return False
        if watched is not self._gallery.viewport():
            return False
        t0 = time.perf_counter()
        visible = visible_row_indices_gallery(self._gallery)
        cap = gallery_max_visible_build()
        visible_count = min(len(visible), cap) if visible else 0
        total = int(self._model.rowCount())
        scroll_val = int(self._gallery.verticalScrollBar().value())
        wheel_ms = (time.perf_counter() - t0) * 1000.0
        UiScrollProfiler.log_wheel_event(
            wheel_event_ms=wheel_ms,
            visible_item_count=visible_count,
            total_gallery_item_count=total,
            view="gallery",
            scroll_value=scroll_val,
        )
        return False
