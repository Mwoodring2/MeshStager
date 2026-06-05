"""Simple tag chip for the Metadata tab (Tier 2.1)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget


class TagChipWidget(QWidget):
    """One tag label; optional remove control for single-select."""

    remove_clicked = Signal(str)

    def __init__(
        self,
        tag: str,
        *,
        removable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tag = tag
        self.setObjectName("TagChip")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 4 if removable else 8, 2)
        row.setSpacing(4)

        label = QLabel(tag)
        label.setObjectName("TagChipLabel")
        row.addWidget(label)

        if removable:
            remove_btn = QPushButton("×")
            remove_btn.setObjectName("TagChipRemove")
            remove_btn.setFlat(True)
            remove_btn.setFixedSize(22, 22)
            remove_btn.setToolTip(f"Remove tag “{tag}”")
            remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self._tag))
            row.addWidget(remove_btn)
