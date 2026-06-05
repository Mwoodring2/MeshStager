"""Shared responsive modal dialog helpers — Yard suite UI standard.

Canonical spec: ``docs/YARD_RESPONSIVE_DIALOG_STANDARD.md``

Applies to MeshStager and all Yard desktop apps. MeshStager is the reference
implementation; copy this module (and ``dialog_placement.py``) when bootstrapping
new Yard tools.

Responsive Dialog Rule
----------------------
All popup/modal windows must be usable on laptop screens.

Required:
- Dialogs are resizable.
- Long dialog content lives inside a scroll area.
- Save, Cancel, Close, Apply, or primary action buttons stay pinned outside the scroll area.
- The user must never need to resize, move, or maximize a dialog just to save or cancel.
- Dialogs must center over the parent window and clamp to the current screen.

Use :class:`ResponsiveModalDialog`, :func:`create_content_scroll_area`, and
:func:`create_pinned_button_row`. Call :func:`finalize_responsive_dialog_show` on show
(via the base class or manually).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from meshcorral.ui.dialog_placement import (
    available_geometry_for_widget,
    center_dialog_over_parent,
    clamp_dialog_size_to_screen,
)
from meshcorral.ui.layout_constants import DIALOG_MIN_WIDTH


class ResponsiveModalDialog(QDialog):
    """
    Laptop-safe modal shell — Yard Responsive Dialog Standard.

    Subclasses with long body copy should place content in :func:`create_content_scroll_area`
    and pin actions with :func:`create_pinned_button_row`.
    """

    responsive_min_width: int = DIALOG_MIN_WIDTH
    responsive_min_height: int = 200

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_responsive_modal(
            self,
            min_width=self.responsive_min_width,
            min_height=self.responsive_min_height,
        )

    def showEvent(self, event: QShowEvent) -> None:
        """Clamp to the work area, then center over the parent window."""
        super().showEvent(event)
        finalize_responsive_dialog_show(
            self,
            self.parentWidget(),
            min_width=self.responsive_min_width,
            min_height=self.responsive_min_height,
        )


def configure_responsive_modal(
    dialog: QDialog,
    *,
    min_width: int,
    min_height: int,
) -> None:
    """Enable resize grip and baseline minimum size for a content-heavy modal."""
    dialog.setSizeGripEnabled(True)
    dialog.setMinimumSize(min_width, min_height)


def create_content_scroll_area(
    parent: QWidget,
    *,
    object_name: str = "DialogScrollArea",
) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    """
    Build a vertical scroll area for dialog body content.

    Primary actions must stay outside this scroll area (pinned bottom row).
    """
    scroll = QScrollArea(parent)
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    content = QWidget()
    content.setObjectName(f"{object_name}Content")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 4, 0)
    layout.setSpacing(12)
    scroll.setWidget(content)
    return scroll, content, layout


def create_pinned_button_row(
    button_widget: QWidget,
    *,
    object_name: str = "DialogButtonRow",
) -> QWidget:
    """Wrap action buttons with bottom padding; keep outside scroll areas."""
    row = QWidget()
    row.setObjectName(object_name)
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 8, 0, 6)
    layout.setSpacing(0)
    layout.addWidget(button_widget)
    return row


def apply_responsive_dialog_geometry(
    dialog: QDialog,
    *,
    min_width: int,
    min_height: int,
) -> None:
    """Clamp *dialog* size to the current screen work area."""
    available = available_geometry_for_widget(dialog)
    if available is None:
        return
    dialog.adjustSize()
    hint = dialog.sizeHint()
    width, height, max_w, max_h, min_w, min_h = clamp_dialog_size_to_screen(
        desired_width=max(min_width, hint.width()),
        desired_height=max(min_height, hint.height()),
        min_width=min_width,
        min_height=min_height,
        available=available,
    )
    dialog.setMinimumSize(min_w, min_h)
    dialog.setMaximumSize(max_w, max_h)
    dialog.resize(width, height)


def finalize_responsive_dialog_show(
    dialog: QDialog,
    parent: QWidget | None,
    *,
    min_width: int,
    min_height: int,
) -> None:
    """Apply geometry clamp, then center over *parent* (call from ``showEvent``)."""
    apply_responsive_dialog_geometry(
        dialog,
        min_width=min_width,
        min_height=min_height,
    )
    center_dialog_over_parent(dialog, parent)


def primary_actions_outside_scroll(
    scroll: QScrollArea | None,
    action_widget: QWidget | None,
) -> bool:
    """Return True when *action_widget* is not nested inside the scroll content."""
    if scroll is None or action_widget is None:
        return False
    scroll_widget = scroll.widget()
    if scroll_widget is None:
        return False
    return action_widget.parent() is not scroll_widget
