"""Prime v1.0 — inspector Preview tab."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from meshcorral.ui.empty_states import PREVIEW_UNAVAILABLE, empty_state_spec
from meshcorral.ui.layout_constants import (
    INSPECTOR_PREVIEW_FRAME_PX,
    INSPECTOR_PREVIEW_MIN_HEIGHT_3D,
    INSPECTOR_PREVIEW_MIN_HEIGHT_IMAGES,
)
from meshcorral.ui.filename_display import filename_tooltip, truncate_filename
from meshcorral.ui.thumbnails.thumbnail_style_rules import default_style_rules
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

_PREVIEW_MIN_3D: int = INSPECTOR_PREVIEW_MIN_HEIGHT_3D
_PREVIEW_MIN_IMAGES: int = INSPECTOR_PREVIEW_MIN_HEIGHT_IMAGES


class PreviewPanel(QWidget):
    """Large preview, filename, type badge, and thumbnail state."""

    regenerate_thumbnail_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preview_max_px = INSPECTOR_PREVIEW_FRAME_PX
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._image_label = QLabel()
        self._image_label.setObjectName("PreviewImage")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumHeight(_PREVIEW_MIN_3D)
        self._image_label.setMaximumHeight(self._preview_max_px)
        self._image_label.setMinimumWidth(180)
        self._image_label.setScaledContents(False)
        root.addWidget(self._image_label)

        self._filename_label = QLabel()
        font = QFont(self._filename_label.font())
        font.setBold(True)
        font.setPointSizeF(max(9.0, font.pointSizeF() + 0.5))
        self._filename_label.setFont(font)
        self._filename_label.setWordWrap(True)
        root.addWidget(self._filename_label)

        self._badge_label = QLabel()
        self._badge_label.setObjectName("InspectorBadge")
        self._badge_label.setWordWrap(True)
        root.addWidget(self._badge_label)

        self._state_label = QLabel()
        self._state_label.setObjectName("PreviewThumbState")
        self._state_label.setWordWrap(True)
        root.addWidget(self._state_label)

        self._sub_label = QLabel()
        self._sub_label.setObjectName("PreviewThumbSubline")
        self._sub_label.setWordWrap(True)
        self._sub_label.hide()
        root.addWidget(self._sub_label)

        self._btn_regenerate = QPushButton("Regenerate thumbnail")
        self._btn_regenerate.setObjectName("SecondaryButton")
        self._btn_regenerate.setToolTip(
            "Queue a Blender thumbnail for this file (.stl / .obj / .fbx)."
        )
        self._btn_regenerate.clicked.connect(self.regenerate_thumbnail_clicked.emit)
        root.addWidget(self._btn_regenerate)

        root.addStretch(1)

    def configure_preview_size(self, *, max_px: int, min_h: int) -> None:
        """Match 3D vs image asset mode preview bounds."""
        self._preview_max_px = max(64, int(max_px))
        self._image_label.setMaximumHeight(self._preview_max_px)
        self._image_label.setMinimumHeight(max(64, int(min_h)))

    def apply(
        self,
        *,
        name: str,
        extension_badge: str,
        thumbnail_state: str,
        preview_kind: str,
        preview_subline: str,
        pixmap: QPixmap | None,
        missing_file: bool,
        preview_blocked_message: str | None,
        can_regenerate: bool,
        blender_enabled: bool,
        preview_thumb_headline: str | None = None,
        preview_thumb_body: str | None = None,
        preview_show_retry_thumbnail: bool | None = None,
        preview_retry_button_label: str | None = None,
        filename_tooltip_text: str = "",
    ) -> None:
        """Populate preview visuals for the current selection."""
        full_name = (filename_tooltip_text or name or "").strip()
        shown = truncate_filename(name or full_name)
        self._filename_label.setText(shown)
        self._filename_label.setToolTip(filename_tooltip(full_name) if full_name else "")
        self._badge_label.setText(f"Type: {extension_badge}")
        if preview_thumb_headline is not None:
            body = (preview_thumb_body or "").strip()
            self._state_label.setText(
                f"{preview_thumb_headline}\n{body}" if body else preview_thumb_headline
            )
        else:
            self._state_label.setText(f"Thumbnail: {thumbnail_state}")

        pk = (preview_kind or "").strip()
        ps = (preview_subline or "").strip()
        if pk:
            self._sub_label.setText(ps if ps else pk)
            self._sub_label.show()
        elif ps:
            self._sub_label.setText(ps)
            self._sub_label.show()
        else:
            self._sub_label.hide()

        if missing_file:
            self._image_label.setPixmap(QPixmap())
            self._image_label.setText("File is missing at this path")
        elif preview_blocked_message:
            self._image_label.clear()
            blocked = empty_state_spec(PREVIEW_UNAVAILABLE)
            self._image_label.setText(
                f"{blocked.title}\n\n{blocked.body}"
            )
        elif pixmap is not None and not pixmap.isNull():
            self._image_label.setText("")
            rules = default_style_rules()
            framed = rules.frame_pixmap_in_square(pixmap, side_px=self._preview_max_px)
            self._image_label.setPixmap(framed)
        else:
            self._image_label.clear()
            self._image_label.setText(ps or "No preview available")

        regen_ok = bool(can_regenerate and not missing_file)
        if preview_show_retry_thumbnail is not None:
            show_btn = bool(
                preview_show_retry_thumbnail and can_regenerate and not missing_file
            )
            self._btn_regenerate.setVisible(show_btn)
            if show_btn and preview_retry_button_label:
                self._btn_regenerate.setText(preview_retry_button_label)
            elif show_btn:
                self._btn_regenerate.setText("Regenerate thumbnail")
            if show_btn:
                self._btn_regenerate.setEnabled(regen_ok)
                tip = (
                    "Queue a thumbnail for this file (uses your current renderer policy)."
                )
                self._btn_regenerate.setToolTip(tip)
        else:
            self._btn_regenerate.setVisible(True)
            self._btn_regenerate.setText("Regenerate thumbnail")
            self._btn_regenerate.setToolTip(
                "Queue a Blender thumbnail for this file (.stl / .obj / .fbx)."
            )
            regen_ok = bool(can_regenerate and blender_enabled and not missing_file)
            self._btn_regenerate.setEnabled(regen_ok)
