"""Minimal user-tags block for the Metadata tab (Tier 2.1)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from meshcorral.ui.tags.tag_chip_widget import TagChipWidget


class TagEditorWidget(QWidget):
    """
    Tags summary, optional chips, and **+ Add Tag** (opens :class:`TagDialog`).

    Multi-select: add-only (no chip remove).
    """

    add_tag_requested = Signal()
    tag_remove_requested = Signal(str)
    tags_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._multi = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        title = QLabel("Tags")
        title.setObjectName("PanelSubTitle")
        root.addWidget(title)

        self._summary = QLabel("No tags assigned")
        self._summary.setObjectName("MutedLabel")
        self._summary.setWordWrap(True)
        root.addWidget(self._summary)

        self._chips_host = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_host)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(6)
        self._chips_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        root.addWidget(self._chips_host)

        self._add_btn = QPushButton("+ Add Tag")
        self._add_btn.setObjectName("SecondaryButton")
        self._add_btn.clicked.connect(self.add_tag_requested.emit)
        self._add_btn.setEnabled(False)
        root.addWidget(self._add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    def set_selection(
        self,
        *,
        paths: list[Path],
        tags: list[str],
        multi: bool,
    ) -> None:
        """Update display for the current selection."""
        self._paths = list(paths)
        self._multi = multi
        enabled = bool(paths)
        self._add_btn.setEnabled(enabled)

        if not paths:
            self._add_btn.setText("+ Add Tag")
            self._summary.setText("Select an asset to assign tags.")
        elif multi:
            self._add_btn.setText(f"+ Add Tag to {len(paths)} Assets")
            if tags:
                self._summary.setText(", ".join(tags))
            else:
                self._summary.setText("No tags on selected assets yet.")
        else:
            self._add_btn.setText("+ Add Tag")
            if tags:
                self._summary.setText(", ".join(tags))
            else:
                self._summary.setText("No tags assigned")

        self._rebuild_chips(tags)

    def _rebuild_chips(self, tags: list[str]) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        removable = bool(self._paths) and not self._multi
        for tag in tags:
            chip = TagChipWidget(tag, removable=removable)
            if removable:
                chip.remove_clicked.connect(self._on_remove)
            self._chips_layout.addWidget(chip)
        self._chips_layout.addStretch(1)

    def _on_remove(self, tag: str) -> None:
        self.tag_remove_requested.emit(tag)
        self.tags_changed.emit()
