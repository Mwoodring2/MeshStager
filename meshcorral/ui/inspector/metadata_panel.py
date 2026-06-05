"""Prime v1.0 — inspector Metadata tab."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from meshcorral.ui.empty_states import METADATA_DEFERRED, empty_state_spec, make_empty_state_widget
from meshcorral.ui.favorites.favorite_toggle_widget import FavoriteToggleWidget
from meshcorral.ui.tags.tag_editor_widget import TagEditorWidget
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_METADATA_MAX_HEIGHT: int = 120


class MetadataPanel(QWidget):
    """Selectable path and file facts with copy actions."""

    copy_path_clicked = Signal()
    copy_metadata_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metadata_copy_text = ""
        self._build_ui()

    def _muted_label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("MutedLabel")
        font = QFont(lab.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        lab.setFont(font)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lab.setWordWrap(True)
        return lab

    def _form_label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("MutedLabel")
        font = QFont(lab.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        lab.setFont(font)
        return lab

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._deferred_banner = make_empty_state_widget(
            empty_state_spec(METADATA_DEFERRED),
            parent=self,
        )
        self._deferred_banner.hide()
        root.addWidget(self._deferred_banner)

        path_row = QVBoxLayout()
        path_row.setSpacing(4)
        path_hdr = QLabel("Path")
        path_hdr.setObjectName("PanelSubTitle")
        path_row.addWidget(path_hdr)
        self._path_value = self._muted_label("—")
        path_row.addWidget(self._path_value)
        root.addLayout(path_row)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        self._folder_value = self._muted_label("—")
        self._ext_value = self._muted_label("—")
        self._size_value = self._muted_label("—")
        self._mod_value = self._muted_label("—")
        self._mode_value = self._muted_label("—")
        self._source_value = self._muted_label("—")
        self._tags_value = self._muted_label("—")
        self._dimensions_value = self._muted_label("—")
        self._faces_value = self._muted_label("—")
        self._vertices_value = self._muted_label("—")
        self._watertight_value = self._muted_label("—")
        self._density_value = self._muted_label("—")
        self._archive_members_value = self._muted_label("—")
        self._cache_meta_value = self._muted_label("—")
        form.addRow(self._form_label("Folder"), self._folder_value)
        form.addRow(self._form_label("Extension"), self._ext_value)
        form.addRow(self._form_label("Size"), self._size_value)
        form.addRow(self._form_label("Modified"), self._mod_value)
        form.addRow(self._form_label("Asset mode"), self._mode_value)
        form.addRow(self._form_label("Metadata source"), self._source_value)
        form.addRow(self._form_label("Dimensions (mm)"), self._dimensions_value)
        form.addRow(self._form_label("Faces"), self._faces_value)
        form.addRow(self._form_label("Vertices"), self._vertices_value)
        form.addRow(self._form_label("Watertight"), self._watertight_value)
        form.addRow(self._form_label("Mesh density"), self._density_value)
        form.addRow(self._form_label("Archive members"), self._archive_members_value)
        form.addRow(self._form_label("Cache status"), self._cache_meta_value)
        form.addRow(self._form_label("Bridge tags"), self._tags_value)
        root.addLayout(form)

        self._favorite_toggle = FavoriteToggleWidget()
        root.addWidget(self._favorite_toggle)

        self._tag_editor = TagEditorWidget()
        root.addWidget(self._tag_editor)

        meta_hdr = QLabel("Metadata block")
        meta_hdr.setObjectName("PanelSubTitle")
        root.addWidget(meta_hdr)
        self._metadata_text = QPlainTextEdit()
        self._metadata_text.setReadOnly(True)
        self._metadata_text.setPlaceholderText("Metadata from Blender jobs will appear here.")
        self._metadata_text.setMaximumHeight(_METADATA_MAX_HEIGHT)
        self._metadata_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        font = QFont(self._metadata_text.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        self._metadata_text.setFont(font)
        root.addWidget(self._metadata_text)

        btn_row = QHBoxLayout()
        self._btn_copy_path = QPushButton("Copy path")
        self._btn_copy_path.clicked.connect(self.copy_path_clicked.emit)
        self._btn_copy_meta = QPushButton("Copy metadata")
        self._btn_copy_meta.setToolTip("Copy tags, stats, and raw JSON to the clipboard.")
        self._btn_copy_meta.clicked.connect(self._on_copy_metadata)
        btn_row.addWidget(self._btn_copy_path)
        btn_row.addWidget(self._btn_copy_meta)
        root.addLayout(btn_row)
        root.addStretch(1)

    def _on_copy_metadata(self) -> None:
        text = self._metadata_copy_text.strip()
        if text:
            QApplication.clipboard().setText(text)
            self.copy_metadata_clicked.emit()

    def apply(
        self,
        *,
        path_str: str,
        folder_display: str,
        extension: str,
        size_display: str,
        modified_display: str,
        asset_mode_display: str,
        metadata_source_display: str,
        dimensions_display: str = "—",
        face_count_display: str = "—",
        vertex_count_display: str = "—",
        watertight_display: str = "—",
        mesh_density_display: str = "—",
        archive_members_display: str = "—",
        cache_status_display: str = "—",
        tags: str,
        metadata_block: str,
        metadata_copy_text: str,
        path_actions_enabled: bool,
        metadata_deferred: bool = False,
    ) -> None:
        """Fill metadata fields for the current asset."""
        if metadata_deferred:
            self._deferred_banner.show()
        else:
            self._deferred_banner.hide()
        self._metadata_copy_text = metadata_copy_text
        self._path_value.setText(path_str)
        self._folder_value.setText(folder_display or "—")
        self._ext_value.setText(extension or "—")
        self._size_value.setText(size_display or "—")
        self._mod_value.setText(modified_display or "—")
        self._mode_value.setText(asset_mode_display or "—")
        self._source_value.setText(metadata_source_display or "Not available")
        self._dimensions_value.setText(dimensions_display or "—")
        self._faces_value.setText(face_count_display or "—")
        self._vertices_value.setText(vertex_count_display or "—")
        self._watertight_value.setText(watertight_display or "—")
        self._density_value.setText(mesh_density_display or "—")
        self._archive_members_value.setText(archive_members_display or "—")
        self._cache_meta_value.setText(cache_status_display or "—")
        self._tags_value.setText(tags or "—")
        self._metadata_text.setPlainText(metadata_block or "")
        enabled = bool(path_actions_enabled and path_str.strip())
        self._btn_copy_path.setEnabled(enabled)
        self._btn_copy_meta.setEnabled(bool(metadata_copy_text.strip()))

    @property
    def tag_editor(self) -> TagEditorWidget:
        """User-defined tags block (Tier 2.1)."""
        return self._tag_editor

    @property
    def favorite_toggle(self) -> FavoriteToggleWidget:
        """Favorite star toggle (Tier 2.2)."""
        return self._favorite_toggle
