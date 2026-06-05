"""Center modal dialogs over a parent window — Yard Responsive Dialog Standard.

See ``docs/YARD_RESPONSIVE_DIALOG_STANDARD.md`` for the permanent suite rule.

- Call :class:`meshcorral.ui.responsive_dialog.ResponsiveModalDialog` or
  :func:`meshcorral.ui.responsive_dialog.configure_responsive_modal` in ``__init__``.
- Put body copy/controls in :func:`create_content_scroll_area` (``QScrollArea``).
- Pin ``QDialogButtonBox`` / primary actions with :func:`create_pinned_button_row`.
- On show, call :func:`finalize_responsive_dialog_show` (clamp + ``center_dialog_over_parent``).

Reference implementation: ``SettingsDialog``.
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QDialog, QWidget

SETTINGS_DIALOG_VERTICAL_MARGIN = 80
SETTINGS_DIALOG_HORIZONTAL_MARGIN = 40


def clamp_dialog_size_to_screen(
    desired_width: int,
    desired_height: int,
    min_width: int,
    min_height: int,
    available: QRect,
    *,
    vertical_margin: int = SETTINGS_DIALOG_VERTICAL_MARGIN,
    horizontal_margin: int = SETTINGS_DIALOG_HORIZONTAL_MARGIN,
) -> tuple[int, int, int, int, int, int]:
    """
    Return clamped size limits for *available* work area.

    ``(width, height, max_width, max_height, effective_min_width, effective_min_height)``
    """
    max_height = max(1, available.height() - vertical_margin)
    max_width = max(1, available.width() - horizontal_margin)
    width = min(max(desired_width, min_width), max_width, available.width())
    height = min(max(desired_height, min_height), max_height, available.height())
    eff_min_w = min(min_width, max_width, available.width())
    eff_min_h = min(min_height, max_height, available.height())
    return width, height, max_width, max_height, eff_min_w, eff_min_h


def available_geometry_for_widget(widget: QWidget) -> QRect | None:
    """Return the screen work area for *widget*, or ``None`` when unknown."""
    screen: QScreen | None = widget.screen()
    if screen is None and widget.parentWidget() is not None:
        screen = widget.parentWidget().screen()
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def center_dialog_over_parent(dialog: QDialog, parent: QWidget | None) -> None:
    """
    Position *dialog* centered on *parent*'s frame, clamped to the screen work area.

    Call after the dialog has a stable size (e.g. from ``showEvent`` or post-``adjustSize``).
    """
    if parent is None or not parent.isVisible():
        _center_on_primary_screen(dialog)
        return

    parent_frame = parent.frameGeometry()
    dialog_frame = dialog.frameGeometry()
    dialog_w = dialog_frame.width()
    dialog_h = dialog_frame.height()
    if dialog_w <= 0 or dialog_h <= 0:
        dialog.adjustSize()
        dialog_frame = dialog.frameGeometry()
        dialog_w = max(1, dialog_frame.width())
        dialog_h = max(1, dialog_frame.height())

    center_x = parent_frame.center().x() - dialog_w // 2
    center_y = parent_frame.center().y() - dialog_h // 2
    target = QRect(center_x, center_y, dialog_w, dialog_h)
    clamped = _clamp_rect_to_screen(target, parent)
    dialog.move(clamped.topLeft())


def _center_on_primary_screen(dialog: QDialog) -> None:
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    dialog_frame = dialog.frameGeometry()
    x = available.center().x() - dialog_frame.width() // 2
    y = available.center().y() - dialog_frame.height() // 2
    dialog.move(_clamp_rect_to_screen(QRect(x, y, dialog_frame.width(), dialog_frame.height()), dialog).topLeft())


def _clamp_rect_to_screen(rect: QRect, widget: QWidget) -> QRect:
    screen = widget.screen()
    if screen is None:
        screen = QApplication.screenAt(rect.center())
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return rect
    available = screen.availableGeometry()
    w = min(rect.width(), available.width())
    h = min(rect.height(), available.height())
    x = max(available.left(), min(rect.left(), available.right() - w + 1))
    y = max(available.top(), min(rect.top(), available.bottom() - h + 1))
    return QRect(x, y, w, h)
