"""Safe relative font scaling for widgets styled with pixel-based stylesheets.

The application stylesheet sets ``QWidget { font-size: 12px; }`` (see
:mod:`meshcorral.ui.theme`), so a polished widget's ``QFont`` carries a *pixel* size and
``QFont.pointSize()`` / ``QFont.pointSizeF()`` report ``-1``. Feeding that ``-1`` back
into ``setPointSize()`` either trips Qt's ``QFont::setPointSize: Point size <= 0``
warning or silently collapses the label to a 1 pt font.

:func:`scale_font_points` picks the axis the font is actually specified on — points,
pixels, or the inherited application font — instead of assuming points.
"""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

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
