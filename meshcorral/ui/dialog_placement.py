"""Center modal dialogs over a parent window — Yard Responsive Dialog Standard.

See ``docs/YARD_RESPONSIVE_DIALOG_STANDARD.md`` for the permanent suite rule.

- Call :class:`meshcorral.ui.responsive_dialog.ResponsiveModalDialog` or
  :func:`meshcorral.ui.responsive_dialog.configure_responsive_modal` in ``__init__``.
- Put body copy/controls in :func:`create_content_scroll_area` (``QScrollArea``).
- Pin ``QDialogButtonBox`` / primary actions with :func:`create_pinned_button_row`.
- On show, call :func:`finalize_responsive_dialog_show` (clamp + ``center_dialog_over_parent``).

Reference implementation: ``SettingsDialog``.

Screen resolution
-----------------
A dialog has no native window handle until it is mapped, so ``QWidget.screen()``
falls back to the *primary* screen. Sizing a dialog against the primary work area
while it is about to appear over a parent on a second monitor produces a dialog
that overhangs (or is clipped by) that monitor. :func:`screen_for_dialog` therefore
resolves the parent window's screen first and only falls back to the dialog's own
screen, the screen under the dialog, and finally the primary screen.

Frame accounting
----------------
``resize()``/``setMaximumSize()`` act on the *client* area, while the work area must
contain the *frame* (title bar and borders). :func:`dialog_frame_extra` measures that
difference so the clamp keeps the whole frame on screen.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize
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
    frame_extra_width: int = 0,
    frame_extra_height: int = 0,
) -> tuple[int, int, int, int, int, int]:
    """
    Return clamped *client* size limits for *available* work area.

    ``frame_extra_width`` / ``frame_extra_height`` are the window-frame overheads from
    :func:`dialog_frame_extra`; they are deducted so the resulting *frame* still fits.

    ``(width, height, max_width, max_height, effective_min_width, effective_min_height)``
    """
    extra_w = max(0, int(frame_extra_width))
    extra_h = max(0, int(frame_extra_height))
    max_height = max(1, available.height() - vertical_margin - extra_h)
    max_width = max(1, available.width() - horizontal_margin - extra_w)
    width = min(max(desired_width, min_width), max_width)
    height = min(max(desired_height, min_height), max_height)
    eff_min_w = min(min_width, max_width)
    eff_min_h = min(min_height, max_height)
    return width, height, max_width, max_height, eff_min_w, eff_min_h


def screen_for_dialog(dialog: QWidget, parent: QWidget | None = None) -> QScreen | None:
    """
    Resolve the screen *dialog* will actually appear on.

    Parent wins: an unmapped dialog reports the primary screen, which is wrong whenever
    the parent window lives on a secondary monitor.
    """
    anchor = parent if parent is not None else dialog.parentWidget()
    screen = _screen_of_window(anchor)
    if screen is None:
        screen = _mapped_screen(dialog)
    if screen is None:
        screen = QApplication.screenAt(dialog.frameGeometry().center())
    if screen is None:
        screen = QApplication.primaryScreen()
    return screen


def available_geometry_for_widget(
    widget: QWidget,
    parent: QWidget | None = None,
) -> QRect | None:
    """Return the screen work area for *widget*, or ``None`` when unknown."""
    screen = screen_for_dialog(widget, parent)
    if screen is None:
        return None
    return screen.availableGeometry()


def dialog_frame_extra(dialog: QWidget) -> tuple[int, int]:
    """
    Return ``(extra_width, extra_height)`` contributed by the window frame.

    Prefers the platform window's reported frame margins, because ``frameGeometry()``
    only picks up the title bar once the window has been mapped.
    """
    handle = dialog.windowHandle()
    if handle is not None:
        margins = handle.frameMargins()
        extra_w = max(0, margins.left() + margins.right())
        extra_h = max(0, margins.top() + margins.bottom())
        if extra_w > 0 or extra_h > 0:
            return extra_w, extra_h
    frame = dialog.frameGeometry()
    geometry = dialog.geometry()
    return (
        max(0, frame.width() - geometry.width()),
        max(0, frame.height() - geometry.height()),
    )


def clamp_frame_rect_to_available(rect: QRect, available: QRect) -> QRect:
    """
    Slide (then shrink) *rect* so it sits fully inside *available*.

    Pure geometry — safe to exercise with synthetic multi-monitor coordinate spaces.
    """
    width = min(rect.width(), available.width())
    height = min(rect.height(), available.height())
    x = max(available.left(), min(rect.left(), available.right() - width + 1))
    y = max(available.top(), min(rect.top(), available.bottom() - height + 1))
    return QRect(x, y, width, height)


def center_dialog_over_parent(dialog: QDialog, parent: QWidget | None) -> None:
    """
    Position *dialog* centered on *parent*'s frame, clamped to that screen's work area.

    Call after the dialog has a stable size (e.g. from ``showEvent`` or post-``adjustSize``).
    """
    available = available_geometry_for_widget(dialog, parent)
    if available is None:
        return
    if parent is None or not parent.isVisible():
        anchor = available
    else:
        anchor = parent.frameGeometry()

    frame_size = _stable_frame_size(dialog)
    target = QRect(
        anchor.center().x() - frame_size.width() // 2,
        anchor.center().y() - frame_size.height() // 2,
        frame_size.width(),
        frame_size.height(),
    )
    dialog.move(clamp_frame_rect_to_available(target, available).topLeft())


def _stable_frame_size(dialog: QWidget) -> QSize:
    """Frame size of *dialog*, re-deriving it when the frame is not measurable yet."""
    frame = dialog.frameGeometry()
    if frame.width() <= 0 or frame.height() <= 0:
        dialog.adjustSize()
        frame = dialog.frameGeometry()
    extra_w, extra_h = dialog_frame_extra(dialog)
    geometry = dialog.geometry()
    return QSize(
        max(1, geometry.width() + extra_w, frame.width()),
        max(1, geometry.height() + extra_h, frame.height()),
    )


def _screen_of_window(widget: QWidget | None) -> QScreen | None:
    """Screen owning *widget*'s top-level window, or ``None`` when not determinable."""
    if widget is None:
        return None
    window = widget.window()
    if window is None:
        return None
    handle = window.windowHandle()
    if handle is not None and handle.screen() is not None:
        return handle.screen()
    return QApplication.screenAt(window.frameGeometry().center())


def _mapped_screen(dialog: QWidget) -> QScreen | None:
    """Screen of *dialog*'s own platform window, or ``None`` before it is mapped."""
    handle = dialog.windowHandle()
    if handle is None:
        return None
    return handle.screen()
