"""Safe relative font scaling for widgets styled with pixel-based stylesheets.

The application stylesheet sets ``QWidget { font-size: 12px; }`` (see
:mod:`meshcorral.ui.theme`), so a polished widget's ``QFont`` carries a *pixel* size and
``QFont.pointSize()`` / ``QFont.pointSizeF()`` report ``-1``. Feeding that ``-1`` back
into ``setPointSize()`` either trips Qt's ``QFont::setPointSize: Point size <= 0``
warning or silently collapses the label to a 1 pt font.

:func:`scale_font_points` picks the axis the font is actually specified on — points,
pixels, or the inherited application font — instead of assuming points.

:func:`ensure_point_sized_font` covers the other half of the problem: *Qt itself* also
derives point sizes from widget fonts. The Windows 11 style reads a combo box's font when
it builds the drop-down popup, so a pixel-only font makes Qt call ``setPointSize(-1)`` and
emit that warning once per process. Restating the same size on the point axis (identical
rendered height at the widget's logical DPI) keeps Qt on a valid axis without changing the
application font or the stylesheet.
"""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QComboBox, QWidget

logger = logging.getLogger(__name__)

DEFAULT_LOGICAL_DPI: Final[float] = 96.0
MIN_POINT_SIZE: Final[float] = 6.5
MIN_PIXEL_SIZE: Final[int] = 6
POINTS_PER_INCH: Final[float] = 72.0


def logical_dpi_for(widget: QWidget | None = None) -> float:
    """Return the logical DPI for *widget*'s screen, falling back to 96."""
    screen = widget.screen() if widget is not None else None
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return DEFAULT_LOGICAL_DPI
    dpi = float(screen.logicalDotsPerInch())
    if dpi <= 0.0:
        return DEFAULT_LOGICAL_DPI
    return dpi


def points_to_pixels(points: float, dpi: float = DEFAULT_LOGICAL_DPI) -> int:
    """Convert a point delta to whole logical pixels at *dpi*."""
    effective_dpi = dpi if dpi > 0.0 else DEFAULT_LOGICAL_DPI
    return int(round(points * effective_dpi / POINTS_PER_INCH))


def pixels_to_points(pixels: int, dpi: float = DEFAULT_LOGICAL_DPI) -> float:
    """Return the point size that renders at *pixels* logical pixels at *dpi*."""
    effective_dpi = dpi if dpi > 0.0 else DEFAULT_LOGICAL_DPI
    return float(pixels) * POINTS_PER_INCH / effective_dpi


def scale_font_points(
    base: QFont,
    delta_points: float,
    *,
    widget: QWidget | None = None,
    min_points: float = MIN_POINT_SIZE,
    min_pixels: int = MIN_PIXEL_SIZE,
) -> QFont:
    """
    Return a copy of *base* resized by *delta_points*, without ever passing Qt ``-1``.

    Resolution order:

    1. ``pointSizeF() > 0`` — a genuine point-sized font, adjusted in points.
    2. ``pixelSize() > 0`` — a stylesheet ``font-size: Npx`` font, adjusted in pixels
       (the point delta is converted using *widget*'s logical DPI).
    3. Neither is set — fall back to the application font's point size.
    """
    font = QFont(base)

    point_size = float(font.pointSizeF())
    if point_size > 0.0:
        font.setPointSizeF(max(min_points, point_size + delta_points))
        return font

    pixel_size = int(font.pixelSize())
    if pixel_size > 0:
        delta_pixels = points_to_pixels(delta_points, logical_dpi_for(widget))
        font.setPixelSize(max(min_pixels, pixel_size + delta_pixels))
        return font

    app_point_size = float(QApplication.font().pointSizeF())
    if app_point_size <= 0.0:
        logger.debug("font scaling: no point or pixel size available; leaving font as-is")
        return font
    font.setPointSizeF(max(min_points, app_point_size + delta_points))
    return font


def point_size_for_inherited_font(widget: QWidget) -> float:
    """
    Return the point size matching *widget*'s current font, or ``0.0`` when unknown.

    Handles all three cases a polished widget can present: a genuine point size (returned
    unchanged), a stylesheet pixel size (converted at the widget's logical DPI so the
    rendered height is identical), and a bare inherited font with neither axis set (falls
    back to the application font). ``0.0`` means "no usable size", so callers must not pass
    the result to Qt.
    """
    font = widget.font()
    point_size = float(font.pointSizeF())
    if point_size > 0.0:
        return point_size

    pixel_size = int(font.pixelSize())
    if pixel_size > 0:
        return pixels_to_points(pixel_size, logical_dpi_for(widget))

    app_point_size = float(QApplication.font().pointSizeF())
    return app_point_size if app_point_size > 0.0 else 0.0


def ensure_combo_box_point_size(combo: QComboBox) -> bool:
    """
    Restate a combo box's inherited pixel font size in points, at the same rendered size.

    The Windows 11 style reads a point size off the combo box when it builds the drop-down
    popup, so a font carrying only a pixel size makes Qt call ``QFont.setPointSize(-1)``.
    The size is restated through the widget's own stylesheet because the application
    stylesheet declares ``font-size`` and therefore outranks :meth:`QWidget.setFont`.

    Polishes *combo* first, since the stylesheet only reaches the font at polish time.
    Returns True when a point size was installed; fonts that already carry one are left
    untouched, so repeated calls are no-ops.
    """
    combo.ensurePolished()
    if float(combo.font().pointSizeF()) > 0.0:
        return False

    points = point_size_for_inherited_font(combo)
    if points <= 0.0:
        logger.debug("font safety: no usable size for combo box; leaving font as-is")
        return False

    points = max(MIN_POINT_SIZE, points)
    existing = combo.styleSheet().strip()
    declaration = f"font-size: {points:g}pt;"
    combo.setStyleSheet(f"{existing}\n{declaration}" if existing else declaration)
    return True


def normalize_combo_box_fonts(root: QWidget) -> int:
    """
    Apply :func:`ensure_combo_box_point_size` to every combo box in *root*'s widget tree.

    Call after the application stylesheet is applied — a theme change re-polishes widgets,
    so newly created combo boxes need the same treatment. Returns how many combo boxes
    were given a point size.
    """
    combos = list(root.findChildren(QComboBox))
    if isinstance(root, QComboBox):
        combos.append(root)
    return sum(1 for combo in combos if ensure_combo_box_point_size(combo))
