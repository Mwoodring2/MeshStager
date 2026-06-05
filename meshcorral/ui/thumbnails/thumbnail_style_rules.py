"""Prime v1.0 — shared thumbnail framing, padding, and color language."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.ui.thumbnails.thumbnail_confidence import ThumbConfidenceState


@dataclass(frozen=True, slots=True)
class ThumbnailBadgeTokens:
    """
    Normalized overlay badge metrics (gallery + table).

    Geometry constants live in :mod:`badge_styles`; this wrapper keeps older call sites.
    """

    ready_side_px: int = 13
    info_side_px: int = 14
    warning_side_px: int = 14
    error_side_px: int = 14
    corner_radius_px: int = 3
    pad_px: int = 1
    background_alpha: int = 228
    background_rgb: tuple[int, int, int] = (30, 32, 38)
    border_rgb: tuple[int, int, int] = (58, 64, 74)
    ready_rgb: tuple[int, int, int] = (96, 178, 104)
    info_rgb: tuple[int, int, int] = (130, 168, 210)
    warning_rgb: tuple[int, int, int] = (230, 176, 96)
    error_rgb: tuple[int, int, int] = (220, 140, 120)

    def side_px_for_health(self, health: ThumbHealth) -> int:
        """Badge edge length for a :class:`ThumbHealth` overlay."""
        from meshcorral.ui.thumbnails.badge_styles import badge_theme_for_mode, resolve_badge_style_kind

        theme = badge_theme_for_mode("dark")
        kind = resolve_badge_style_kind(health=health)
        return theme.style_for(kind).side_px

    def foreground_for_health(self, health: ThumbHealth) -> tuple[int, int, int]:
        """Glyph color for *health*."""
        from meshcorral.ui.thumbnails.badge_styles import badge_theme_for_mode, resolve_badge_style_kind

        theme = badge_theme_for_mode("dark")
        kind = resolve_badge_style_kind(health=health)
        return theme.style_for(kind).fg_rgb

    def glyph_for_health(self, health: ThumbHealth) -> str:
        """Single-character badge glyph."""
        from meshcorral.ui.thumbnails.badge_styles import badge_theme_for_mode, resolve_badge_style_kind

        theme = badge_theme_for_mode("dark")
        kind = resolve_badge_style_kind(health=health)
        return theme.style_for(kind).glyph

    def glyph_point_size(self, side_px: int) -> float:
        """Font size for the badge glyph."""
        return max(6.5, min(10.0, side_px * 0.58))


@dataclass(frozen=True, slots=True)
class ThumbnailCardTextColors:
    """Typography colors baked into format-card pixmaps."""

    title_rgb: tuple[int, int, int]
    subtitle_rgb: tuple[int, int, int]
    muted_subtitle_rgb: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ThumbnailStyleRules:
    """
    Visual constants for format cards and placeholder tiles.

    Keeps gallery/table thumbnails intentionally rendered and on-brand.
    """

    card_background_alpha: int = 235
    card_corner_radius_ratio: float = 0.08
    card_inner_margin_px: int = 2
    title_area_height_ratio: float = 0.55
    subtitle_y_ratio: float = 0.62
    title_color_rgb: tuple[int, int, int] = (245, 245, 245)
    subtitle_color_rgb: tuple[int, int, int] = (235, 235, 235)
    neutral_base_rgb: tuple[int, int, int] = (90, 90, 96)
    portrait_aspect_break: float = 1.25
    landscape_aspect_break: float = 0.8
    scan_density_large_folder: int = 2000
    scan_density_tight_padding: int = 4
    scan_density_normal_padding: int = 6
    thumbnail_content_padding_ratio: float = 0.06
    thumbnail_min_fill_ratio: float = 0.72

    def corner_radius_px(self, side_px: int) -> int:
        """Rounded-rect radius for a square card of *side_px*."""
        side = max(16, int(side_px))
        return max(4, int(side * self.card_corner_radius_ratio))

    def content_padding_px(self, *, record_count: int = 0) -> int:
        """Inner padding; tighter when the working set is very large."""
        if record_count >= self.scan_density_large_folder:
            return self.scan_density_tight_padding
        return self.scan_density_normal_padding

    def badge_tokens(self, theme_mode: str = "dark") -> ThumbnailBadgeTokens:
        """Overlay badge tokens for *theme_mode* (``dark`` or ``light``)."""
        from meshcorral.ui.thumbnails import badge_styles

        theme = badge_styles.badge_theme_for_mode(theme_mode)
        ready = theme.ready
        info = theme.info
        warn = theme.timeout
        err = theme.failed
        return ThumbnailBadgeTokens(
            ready_side_px=ready.side_px,
            info_side_px=info.side_px,
            warning_side_px=warn.side_px,
            error_side_px=err.side_px,
            corner_radius_px=badge_styles.BADGE_CORNER_RADIUS,
            pad_px=badge_styles.BADGE_PADDING,
            background_alpha=badge_styles.BADGE_OPACITY,
            background_rgb=ready.fill_rgb,
            border_rgb=ready.border_rgb,
            ready_rgb=ready.fg_rgb,
            info_rgb=info.fg_rgb,
            warning_rgb=warn.fg_rgb,
            error_rgb=err.fg_rgb,
        )

    def card_text_colors(self, theme_mode: str = "dark") -> ThumbnailCardTextColors:
        """Title/subtitle colors for painted format cards."""
        if theme_mode == "light":
            return ThumbnailCardTextColors(
                title_rgb=(26, 28, 34),
                subtitle_rgb=(52, 56, 64),
                muted_subtitle_rgb=(108, 114, 124),
            )
        return ThumbnailCardTextColors(
            title_rgb=self.title_color_rgb,
            subtitle_rgb=self.subtitle_color_rgb,
            muted_subtitle_rgb=(168, 174, 184),
        )

    def card_background_alpha_for(self, confidence: ThumbConfidenceState) -> int:
        """Card fill alpha — deferred is calmer; failures slightly stronger."""
        if confidence == ThumbConfidenceState.DEFERRED:
            return 188
        if confidence in (
            ThumbConfidenceState.FAILED,
            ThumbConfidenceState.CORRUPT,
        ):
            return 242
        if confidence == ThumbConfidenceState.TIMEOUT:
            return 220
        if confidence == ThumbConfidenceState.UNSUPPORTED:
            return 210
        return self.card_background_alpha

    def confidence_tint_rgb(
        self,
        base_rgb: tuple[int, int, int],
        *,
        confidence: ThumbConfidenceState,
        health: ThumbHealth | None = None,
    ) -> tuple[int, int, int]:
        """
        Adjust base format color by lifecycle confidence (not only index health).

        Deferred stays informational; failures read as warnings/errors.
        """
        r, g, b = base_rgb
        if confidence == ThumbConfidenceState.DEFERRED:
            return (
                int(r * 0.88 + 18),
                int(g * 0.90 + 18),
                int(b * 0.92 + 22),
            )
        if confidence == ThumbConfidenceState.UNSUPPORTED:
            return (int(r * 0.86), int(g * 0.86), int(b * 0.88))
        if confidence == ThumbConfidenceState.CORRUPT:
            return (min(168, int(r * 1.2) + 28), int(g * 0.62), int(b * 0.62))
        if confidence == ThumbConfidenceState.FAILED:
            return (min(160, int(r * 1.15) + 20), int(g * 0.75), int(b * 0.75))
        if confidence == ThumbConfidenceState.TIMEOUT:
            return (min(148, int(r * 1.08) + 22), int(g * 0.86), int(b * 0.70))
        if confidence in (
            ThumbConfidenceState.GENERATING,
            ThumbConfidenceState.QUEUED,
            ThumbConfidenceState.DECODING,
            ThumbConfidenceState.PENDING,
        ):
            return (int(r * 0.94), int(g * 0.96), int(b * 0.98))
        if health is not None:
            return self.health_tint_rgb(base_rgb, health=health)
        return base_rgb

    def health_tint_rgb(
        self,
        base_rgb: tuple[int, int, int],
        *,
        health: ThumbHealth,
    ) -> tuple[int, int, int]:
        """Adjust base format color for thumb health (subdued, not alarmist)."""
        r, g, b = base_rgb
        if health == ThumbHealth.FAILED_THUMBNAIL:
            return (min(160, int(r * 1.15) + 20), int(g * 0.75), int(b * 0.75))
        if health == ThumbHealth.MISSING_THUMBNAIL:
            return (int(r * 0.95), int(g * 0.95), int(b * 0.95))
        if health == ThumbHealth.UNSUPPORTED:
            return (int(r * 0.9), int(g * 0.9), int(b * 0.9))
        return base_rgb

    def thumbnail_content_padding_px(self, side_px: int) -> int:
        """Inner padding when fitting a decoded thumb into a square cell."""
        side = max(16, int(side_px))
        return max(2, int(side * self.thumbnail_content_padding_ratio))

    def frame_pixmap_in_square(self, source: QPixmap, *, side_px: int) -> QPixmap:
        """
        Scale *source* into a square canvas with even padding (aspect preserved).

        Display-only helper; does not change decode or routing behavior.
        """
        side = max(16, int(side_px))
        if source.isNull():
            return QPixmap(side, side)

        pad = self.thumbnail_content_padding_px(side)
        inner = max(8, side - 2 * pad)
        scaled = source.scaled(
            inner,
            inner,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(side, side)
        canvas.fill(Qt.GlobalColor.transparent)
        x = (side - scaled.width()) // 2
        y = (side - scaled.height()) // 2
        from PySide6.QtGui import QPainter

        painter = QPainter(canvas)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return canvas

    def fit_mode_for_aspect(self, width: int, height: int) -> str:
        """
        Return ``portrait``, ``landscape``, or ``square`` for silhouette framing hints.

        Used by future exposure normalization; cards remain square today.
        """
        w = max(1, int(width))
        h = max(1, int(height))
        ratio = w / float(h)
        if ratio >= self.portrait_aspect_break:
            return "landscape"
        if ratio <= self.landscape_aspect_break:
            return "portrait"
        return "square"


def default_style_rules() -> ThumbnailStyleRules:
    """Default Roundup thumbnail style (Prime v1.0)."""
    return ThumbnailStyleRules()
