"""Star toggle for favoriting the current selection (Tier 2.2)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


class FavoriteToggleWidget(QWidget):
    """Checkable ☆ / ★ control for one selected asset."""

    favorite_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._btn = QToolButton()
        self._btn.setCheckable(True)
        self._btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn.setToolTip("Mark this asset as a favorite for quick filtering.")
        self._btn.clicked.connect(self._on_clicked)
        layout.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.set_enabled(False)
        self.set_favorite(False)

    def set_enabled(self, enabled: bool) -> None:
        """Enable only for single selection."""
        self._btn.setEnabled(enabled)

    def set_favorite(self, favorite: bool) -> None:
        """Update checked state without emitting."""
        self._btn.blockSignals(True)
        self._btn.setChecked(favorite)
        self._btn.setText("★ Favorited" if favorite else "☆ Favorite")
        self._btn.blockSignals(False)

    def _on_clicked(self) -> None:
        self._btn.setText("★ Favorited" if self._btn.isChecked() else "☆ Favorite")
        self.favorite_toggled.emit(self._btn.isChecked())
