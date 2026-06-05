"""Prime v1.0 — inspector Actions tab and multi-selection actions."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from meshcorral.ui.empty_states import (
    MULTI_SELECTION,
    empty_state_spec,
    make_empty_state_widget,
)
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AssetActionsPanel(QWidget):
    """Quick actions for a single selected asset."""

    open_file_clicked = Signal()
    reveal_in_explorer_clicked = Signal()
    copy_path_clicked = Signal()
    regenerate_thumbnail_clicked = Signal()
    open_thumbnail_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._open_thumb_path = ""
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self._btn_open = QPushButton("Open file")
        self._btn_open.clicked.connect(self.open_file_clicked.emit)
        self._btn_reveal = QPushButton("Reveal in Explorer")
        self._btn_reveal.setToolTip("Open the folder containing this file.")
        self._btn_reveal.clicked.connect(self.reveal_in_explorer_clicked.emit)
        self._btn_copy = QPushButton("Copy path")
        self._btn_copy.clicked.connect(self.copy_path_clicked.emit)
        self._btn_regenerate = QPushButton("Regenerate thumbnail")
        self._btn_regenerate.setObjectName("SecondaryButton")
        self._btn_regenerate.clicked.connect(self.regenerate_thumbnail_clicked.emit)
        self._btn_open_thumb = QPushButton("Open thumbnail")
        self._btn_open_thumb.setToolTip("Open the generated Blender thumbnail in the default viewer.")
        self._btn_open_thumb.clicked.connect(self._on_open_thumbnail)

        grid.addWidget(self._btn_open, 0, 0)
        grid.addWidget(self._btn_reveal, 0, 1)
        grid.addWidget(self._btn_copy, 1, 0)
        grid.addWidget(self._btn_regenerate, 1, 1)
        grid.addWidget(self._btn_open_thumb, 2, 0, 1, 2)
        root.addLayout(grid)
        root.addStretch(1)

    def _on_open_thumbnail(self) -> None:
        if self._open_thumb_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._open_thumb_path))
        self.open_thumbnail_clicked.emit()

    def set_open_thumbnail_path(self, path: str) -> None:
        """Remember Blender thumbnail path for Open thumbnail."""
        self._open_thumb_path = path.strip()

    def apply(
        self,
        *,
        missing_file: bool,
        path_enabled: bool,
        can_regenerate: bool,
        has_blender_thumbnail: bool,
        blender_enabled: bool,
    ) -> None:
        """Enable or disable action buttons for the current asset."""
        path_ok = bool(path_enabled) and not missing_file
        self._btn_open.setEnabled(path_ok)
        self._btn_reveal.setEnabled(bool(path_enabled))
        self._btn_copy.setEnabled(bool(path_enabled))
        regen = bool(can_regenerate and blender_enabled and not missing_file)
        self._btn_regenerate.setEnabled(regen)
        has_thumb = bool(
            has_blender_thumbnail and self._open_thumb_path and not missing_file
        )
        self._btn_open_thumb.setEnabled(has_thumb)


class InspectorMultiActionsPanel(QWidget):
    """Batch actions when multiple assets are selected."""

    batch_queue_thumbnails_clicked = Signal()
    batch_copy_paths_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(10)
        self._summary_host = make_empty_state_widget(
            empty_state_spec(MULTI_SELECTION),
            parent=self,
        )
        root.addWidget(self._summary_host)
        self._count_label = QLabel()
        self._count_label.setObjectName("MutedLabel")
        self._count_label.setWordWrap(True)
        root.addWidget(self._count_label)

        hdr = QLabel("Selection actions")
        hdr.setObjectName("PanelSubTitle")
        root.addWidget(hdr)

        self._btn_batch_queue = QPushButton("Queue Blender thumbnails")
        self._btn_batch_queue.setToolTip(
            "Queue thumbnail jobs for all selected .stl and .obj files."
        )
        self._btn_batch_queue.clicked.connect(self.batch_queue_thumbnails_clicked.emit)
        root.addWidget(self._btn_batch_queue)

        self._btn_batch_copy = QPushButton("Copy all paths")
        self._btn_batch_copy.clicked.connect(self.batch_copy_paths_clicked.emit)
        root.addWidget(self._btn_batch_copy)
        root.addStretch(1)

    def apply(self, *, count: int, mesh_count: int, blender_enabled: bool) -> None:
        """Update multi-select summary and action availability."""
        self._count_label.setText(
            f"{count} asset(s) selected."
            + (
                f"  ({mesh_count} are .stl / .obj / .fbx — can queue Blender thumbnails.)"
                if mesh_count
                else ""
            )
        )
        queue_ok = bool(mesh_count > 0 and blender_enabled)
        self._btn_batch_queue.setEnabled(queue_ok)
