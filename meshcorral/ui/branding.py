"""Reusable brand header for Yard desktop apps (MeshStager and suite)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

HEADER_ICON_DISPLAY_PX = 40
HEADER_ICON_TITLE_SPACING_PX = 10


class BrandHeader(QFrame):
    """
    Top brand strip: icon, app title, subtitle, and optional right-side actions.

    Object names: ``BrandHeader``, ``BrandTitle``, ``BrandSubtitle`` (for styling).
    """

    def __init__(
        self,
        app_name: str,
        subtitle: str,
        icon_path: str | Path | None = None,
        right_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BrandHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(HEADER_ICON_TITLE_SPACING_PX)

        display_px = HEADER_ICON_DISPLAY_PX
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(QSize(display_px, display_px))
        self.icon_label.setAlignment(Qt.AlignCenter)

        if icon_path:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                self.icon_label.setPixmap(
                    pixmap.scaled(
                        display_px,
                        display_px,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )

        layout.addWidget(self.icon_label)

        text_stack = QVBoxLayout()
        text_stack.setSpacing(0)

        title = QLabel(app_name)
        title.setObjectName("BrandTitle")

        sub = QLabel(subtitle)
        sub.setObjectName("BrandSubtitle")

        text_stack.addWidget(title)
        text_stack.addWidget(sub)

        layout.addLayout(text_stack)
        layout.addStretch()

        if right_widget is not None:
            layout.addWidget(right_widget)
