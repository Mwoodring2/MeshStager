"""Prime v1.0 RC — consistent health badges for gallery and table overlays."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.badge_styles import (
    BADGE_BORDER_WIDTH,
    BADGE_CORNER_RADIUS,
    BADGE_MARGIN,
    BADGE_OPACITY,
    BADGE_PADDING,
    BADGE_SELECTED_OPACITY,
    BADGE_SIZE_MEDIUM,
    BADGE_SIZE_SMALL,
    BadgeStyleKind,
    ThumbnailBadgeStyle,
    badge_theme_for_mode,
    gallery_badge_rect,
    resolve_badge_style_kind,
)

_BADGE_PIXMAP_SIZES: tuple[int, ...] = (14, 13, 15, 16)


def _badge_side_from_icon(icon: QIcon) -> int:
    """Best-effort edge length from an icon."""
    for side in _BADGE_PIXMAP_SIZES:
        pm = icon.pixmap(side, side)
        if not pm.isNull():
            return pm.width()
    pm = icon.pixmap(BADGE_SIZE_MEDIUM, BADGE_SIZE_MEDIUM)
    return pm.width() if not pm.isNull() else BADGE_SIZE_MEDIUM


def build_badge_icon(
    kind: BadgeStyleKind,
    *,
    theme_mode: str = "dark",
    selected: bool = False,
) -> QIcon:
    """Render a square badge :class:`QIcon` for *kind*."""
    theme = badge_theme_for_mode(theme_mode)
    style = theme.style_for(kind)
    return QIcon(_render_badge_pixmap(style, selected=selected))


def build_health_badge_icon(
    health: ThumbHealth,
    *,
    theme_mode: str = "dark",
    visual: ThumbVisualState | None = None,
    generating: bool = False,
    queued: bool = False,
    decoding: bool = False,
    bridge_error_message: str | None = None,
    selected: bool = False,
) -> QIcon:
    """
    Render a badge for :class:`ThumbHealth` plus optional paint flags.

    Backward-compatible entry point; prefers :func:`resolve_badge_style_kind`.
    """
    kind = resolve_badge_style_kind(
        health=health,
        visual=visual,
        generating=generating,
        queued=queued,
        decoding=decoding,
        bridge_error_message=bridge_error_message,
    )
    return build_badge_icon(kind, theme_mode=theme_mode, selected=selected)


def paint_badge_pixmap(
    painter: QPainter,
    x: int,
    y: int,
    pixmap: QPixmap,
) -> None:
    """Draw a pre-rendered badge pixmap at ``(x, y)``."""
    if pixmap.isNull():
        return
    painter.drawPixmap(int(x), int(y), pixmap)


def paint_gallery_badge(
    painter: QPainter,
    thumb_x: int,
    thumb_y: int,
    thumb_w: int,
    thumb_h: int,
    icon: QIcon,
) -> None:
    """Paint a status badge anchored to the bottom-right of a gallery thumbnail."""
    if icon.isNull():
        return
    pm = icon.pixmap(BADGE_SIZE_MEDIUM, BADGE_SIZE_MEDIUM)
    if pm.isNull():
        return
    bx, by = gallery_badge_rect(thumb_x, thumb_y, thumb_w, thumb_h, pm.width())
    paint_badge_pixmap(painter, bx, by, pm)


def _render_badge_pixmap(style: ThumbnailBadgeStyle, *, selected: bool = False) -> QPixmap:
    side = max(10, int(style.side_px))
    pm = QPixmap(side, side)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pad = BADGE_PADDING
    inner = side - 2 * pad
    fill = QColor(int(style.fill_rgb[0]), int(style.fill_rgb[1]), int(style.fill_rgb[2]))
    alpha = style.selected_opacity() if selected else style.opacity
    fill.setAlpha(alpha)
    border = QColor(int(style.border_rgb[0]), int(style.border_rgb[1]), int(style.border_rgb[2]))
    painter.setPen(QPen(border, BADGE_BORDER_WIDTH))
    painter.setBrush(fill)
    painter.drawRoundedRect(pad, pad, inner, inner, BADGE_CORNER_RADIUS, BADGE_CORNER_RADIUS)

    fg = QColor(int(style.fg_rgb[0]), int(style.fg_rgb[1]), int(style.fg_rgb[2]))
    painter.setPen(fg)
    font = QFont()
    font.setBold(True)
    font.setPointSizeF(max(6.5, min(10.0, side * 0.58)))
    painter.setFont(font)
    painter.drawText(
        QRect(pad, pad, inner, inner),
        int(Qt.AlignmentFlag.AlignCenter),
        style.glyph,
    )
    painter.end()
    return pm
