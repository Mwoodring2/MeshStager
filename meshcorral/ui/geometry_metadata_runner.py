"""Background worker for STL/OBJ geometry metadata (Prime v1.0 Sprint E)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from meshcorral.services.metadata.geometry_metadata import extract_geometry_metadata

logger = logging.getLogger(__name__)


class GeometryMetadataRunner(QObject):
    """
    Extract mesh stats off the UI thread.

    Emits :pyattr:`summary_ready` with ``(path_key, AssetMetadataSummary)``.
    """

    summary_ready = Signal(str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @Slot(str, int, bool)
    def extract_for_path(
        self,
        path_s: str,
        size_bytes: int,
        allow_large: bool,
    ) -> None:
        """Run geometry extraction for one file path."""
        path = Path(path_s)
        size = int(size_bytes) if size_bytes >= 0 else None
        summary = extract_geometry_metadata(
            path,
            size_bytes=size,
            allow_large=bool(allow_large),
        )
        try:
            self.summary_ready.emit(path_s, summary)
        except RuntimeError:
            logger.debug("summary_ready emit aborted: signal source deleted")
