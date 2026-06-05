"""Prime v1.0 — format-card placeholder rendering."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.thumbnail_confidence import (
    ThumbConfidenceState,
    _CARD_OVERRIDE_CONFIDENCE,
    confidence_state_for,
)
from meshcorral.ui.thumbnails.thumbnail_style_rules import ThumbnailStyleRules, default_style_rules
from meshcorral.ui.thumbnails.unsupported_visuals import format_card_title, resolve_unsupported_visual
from meshcorral.utils.filesize_display import format_file_size_display


def _record_size_bytes(record: FileRecord) -> int:
    """Safe size for paint paths (metadata may not be enriched yet)."""
    raw = record.size_bytes
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def card_base_color(
    extension: str,
    *,
    health: ThumbHealth,
    visual: ThumbVisualState,
    style: ThumbnailStyleRules | None = None,
    size_bytes: int = 0,
    deferred: bool = False,
    confidence: ThumbConfidenceState | None = None,
    theme_mode: str = "dark",
    bridge_error_message: str | None = None,
) -> QColor:
    """Background fill for a format card."""
    rules = style or default_style_rules()
    conf = confidence or confidence_state_for(
        visual,
        health=health,
        deferred=deferred,
        bridge_error_message=bridge_error_message,
    )
    identity = resolve_unsupported_visual(
        extension,
        health=health,
        visual=visual,
        size_bytes=size_bytes,
        deferred=deferred,
        bridge_error_message=bridge_error_message,
    )
    rgb = rules.confidence_tint_rgb(
        identity.base_rgb,
        confidence=conf,
        health=health,
    )
    color = QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    color.setAlpha(rules.card_background_alpha_for(conf))
    return color


def build_format_card_icon(
    record: FileRecord,
    *,
    visual: ThumbVisualState,
    health: ThumbHealth,
    px: int,
    generating: bool = False,
    deferred: bool = False,
    style: ThumbnailStyleRules | None = None,
    working_set_count: int = 0,
    theme_mode: str = "dark",
    bridge_error_message: str | None = None,
) -> QIcon:
    """
    Render a square format-card :class:`QIcon` for non-raster or not-yet-ready rows.

    Centralizes Prime v1.0 visual language (padding, typography, confidence subtitle).
    """
    rules = style or default_style_rules()
    text_colors = rules.card_text_colors(theme_mode)
    ext = (record.extension or record.path.suffix or "").lower().strip()
    identity = resolve_unsupported_visual(
        ext,
        health=health,
        visual=visual,
        size_bytes=_record_size_bytes(record),
        deferred=deferred,
        bridge_error_message=bridge_error_message,
    )
    confidence = confidence_state_for(
        visual,
        health=health,
        generating=generating,
        deferred=deferred,
        bridge_error_message=bridge_error_message,
    )
    title = (
        confidence.card_title()
        if confidence in _CARD_OVERRIDE_CONFIDENCE
        else format_card_title(ext, identity=identity)
    )
    subtitle = confidence.card_subtitle()
    size_s = format_file_size_display(record.size_bytes)

    side = max(16, min(512, int(px)))
    pm = QPixmap(side, side)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin = rules.card_inner_margin_px
    pad = rules.content_padding_px(record_count=working_set_count)
    painter.setBrush(
        card_base_color(
            ext,
            health=health,
            visual=visual,
            style=rules,
            size_bytes=_record_size_bytes(record),
            deferred=deferred,
            confidence=confidence,
            theme_mode=theme_mode,
            bridge_error_message=bridge_error_message,
        )
    )
    painter.setPen(Qt.PenStyle.NoPen)
    radius = rules.corner_radius_px(side)
    painter.drawRoundedRect(margin, margin, side - 2 * margin, side - 2 * margin, radius, radius)

    tr, tg, tb = text_colors.title_rgb
    painter.setPen(QColor(tr, tg, tb))
    f1 = QFont()
    f1.setBold(True)
    title_pt = max(7.0, min(18.0, side / 7.5))
    if health == ThumbHealth.UNSUPPORTED and not deferred:
        title_pt = max(7.0, min(14.0, side / 9.0))
    f1.setPointSizeF(title_pt)
    painter.setFont(f1)
    title_rect = QRect(pad, 10, side - 2 * pad, int(side * rules.title_area_height_ratio))
    _draw_elided_centered(painter, title_rect, title)

    muted = confidence.is_informational()
    sr, sg, sb = (
        text_colors.muted_subtitle_rgb if muted else text_colors.subtitle_rgb
    )
    painter.setPen(QColor(sr, sg, sb))
    f2 = QFont()
    f2.setBold(False)
    f2.setPointSizeF(max(6.5, min(11.0, side / 11.0)))
    painter.setFont(f2)
    ext_s = ext if ext else "—"
    line1 = f"{ext_s}  {size_s}"
    y0 = int(side * rules.subtitle_y_ratio)
    line1_rect = QRect(pad, y0, side - 2 * pad, int(side * 0.18))
    _draw_elided_centered(painter, line1_rect, line1)
    line2 = subtitle if subtitle else f"{identity.badge}"
    line2_rect = QRect(pad, y0 + int(side * 0.16), side - 2 * pad, int(side * 0.18))
    _draw_elided_centered(painter, line2_rect, line2)
    painter.end()
    return QIcon(pm)


def _draw_elided_centered(painter: QPainter, rect: QRect, text: str) -> None:
    """Draw *text* centered in *rect*, eliding when wider than the cell."""
    fm = painter.fontMetrics()
    elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, max(8, rect.width()))
    painter.drawText(
        rect,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        elided,
    )
