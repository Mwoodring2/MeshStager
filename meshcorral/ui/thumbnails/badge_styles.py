"""Prime v1.0 RC A5.2 — badge metrics and per-state style tokens."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.thumbnail_ux_copy import classify_bridge_error_kind

# Shared geometry (gallery + table overlays)
BADGE_SIZE_SMALL: int = 13
BADGE_SIZE_MEDIUM: int = 14
BADGE_PADDING: int = 1
BADGE_CORNER_RADIUS: int = 3
BADGE_MARGIN: int = 3
BADGE_BORDER_WIDTH: int = 1
BADGE_OPACITY: int = 228
BADGE_SELECTED_OPACITY: int = 248


class BadgeStyleKind(str, Enum):
    """Visual badge families (shared geometry, distinct colors)."""

    READY = "ready"
    INFO = "info"
    DEFERRED = "deferred"
    UNSUPPORTED = "unsupported"
    PROGRESS = "progress"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class ThumbnailBadgeStyle:
    """Paint tokens for one badge state."""

    kind: BadgeStyleKind
    side_px: int
    fill_rgb: tuple[int, int, int]
    border_rgb: tuple[int, int, int]
    fg_rgb: tuple[int, int, int]
    opacity: int
    glyph: str

    def selected_opacity(self) -> int:
        """Slightly stronger fill when the parent cell is selected."""
        return min(255, int(self.opacity * 1.08) + 8)


@dataclass(frozen=True, slots=True)
class ThumbnailBadgeTheme:
    """All badge styles for one UI theme."""

    ready: ThumbnailBadgeStyle
    info: ThumbnailBadgeStyle
    deferred: ThumbnailBadgeStyle
    unsupported: ThumbnailBadgeStyle
    progress: ThumbnailBadgeStyle
    failed: ThumbnailBadgeStyle
    timeout: ThumbnailBadgeStyle
    corrupt: ThumbnailBadgeStyle

    def style_for(self, kind: BadgeStyleKind) -> ThumbnailBadgeStyle:
        """Return the style for *kind*."""
        return getattr(self, kind.value)


def badge_theme_dark() -> ThumbnailBadgeTheme:
    """Dark-theme badge palette."""
    return ThumbnailBadgeTheme(
        ready=ThumbnailBadgeStyle(
            BadgeStyleKind.READY,
            BADGE_SIZE_SMALL,
            (34, 42, 38),
            (58, 72, 64),
            (96, 178, 104),
            BADGE_OPACITY,
            "✓",
        ),
        info=ThumbnailBadgeStyle(
            BadgeStyleKind.INFO,
            BADGE_SIZE_MEDIUM,
            (34, 38, 46),
            (58, 64, 76),
            (130, 168, 210),
            BADGE_OPACITY,
            "i",
        ),
        deferred=ThumbnailBadgeStyle(
            BadgeStyleKind.DEFERRED,
            BADGE_SIZE_MEDIUM,
            (36, 40, 48),
            (60, 66, 78),
            (148, 158, 176),
            BADGE_OPACITY,
            "…",
        ),
        unsupported=ThumbnailBadgeStyle(
            BadgeStyleKind.UNSUPPORTED,
            BADGE_SIZE_MEDIUM,
            (38, 38, 42),
            (62, 62, 70),
            (156, 156, 168),
            BADGE_OPACITY,
            "—",
        ),
        progress=ThumbnailBadgeStyle(
            BadgeStyleKind.PROGRESS,
            BADGE_SIZE_MEDIUM,
            (36, 40, 44),
            (60, 66, 72),
            (168, 176, 184),
            BADGE_OPACITY,
            "◎",
        ),
        failed=ThumbnailBadgeStyle(
            BadgeStyleKind.FAILED,
            BADGE_SIZE_MEDIUM,
            (52, 36, 34),
            (88, 58, 54),
            (220, 140, 120),
            BADGE_OPACITY,
            "!",
        ),
        timeout=ThumbnailBadgeStyle(
            BadgeStyleKind.TIMEOUT,
            BADGE_SIZE_MEDIUM,
            (50, 42, 30),
            (86, 72, 48),
            (230, 176, 96),
            BADGE_OPACITY,
            "↻",
        ),
        corrupt=ThumbnailBadgeStyle(
            BadgeStyleKind.CORRUPT,
            BADGE_SIZE_MEDIUM,
            (56, 32, 32),
            (92, 52, 52),
            (232, 118, 118),
            BADGE_OPACITY,
            "×",
        ),
    )


def badge_theme_light() -> ThumbnailBadgeTheme:
    """Light-theme badge palette."""
    return ThumbnailBadgeTheme(
        ready=ThumbnailBadgeStyle(
            BadgeStyleKind.READY,
            BADGE_SIZE_SMALL,
            (236, 248, 238),
            (168, 198, 172),
            (27, 110, 36),
            BADGE_OPACITY,
            "✓",
        ),
        info=ThumbnailBadgeStyle(
            BadgeStyleKind.INFO,
            BADGE_SIZE_MEDIUM,
            (236, 242, 252),
            (176, 188, 206),
            (26, 98, 210),
            BADGE_OPACITY,
            "i",
        ),
        deferred=ThumbnailBadgeStyle(
            BadgeStyleKind.DEFERRED,
            BADGE_SIZE_MEDIUM,
            (240, 242, 246),
            (186, 190, 198),
            (98, 108, 124),
            BADGE_OPACITY,
            "…",
        ),
        unsupported=ThumbnailBadgeStyle(
            BadgeStyleKind.UNSUPPORTED,
            BADGE_SIZE_MEDIUM,
            (242, 242, 244),
            (190, 190, 196),
            (108, 110, 118),
            BADGE_OPACITY,
            "—",
        ),
        progress=ThumbnailBadgeStyle(
            BadgeStyleKind.PROGRESS,
            BADGE_SIZE_MEDIUM,
            (240, 242, 244),
            (186, 190, 196),
            (88, 96, 108),
            BADGE_OPACITY,
            "◎",
        ),
        failed=ThumbnailBadgeStyle(
            BadgeStyleKind.FAILED,
            BADGE_SIZE_MEDIUM,
            (252, 238, 234),
            (210, 170, 160),
            (198, 72, 48),
            BADGE_OPACITY,
            "!",
        ),
        timeout=ThumbnailBadgeStyle(
            BadgeStyleKind.TIMEOUT,
            BADGE_SIZE_MEDIUM,
            (255, 246, 230),
            (220, 196, 150),
            (210, 132, 26),
            BADGE_OPACITY,
            "↻",
        ),
        corrupt=ThumbnailBadgeStyle(
            BadgeStyleKind.CORRUPT,
            BADGE_SIZE_MEDIUM,
            (255, 232, 232),
            (210, 150, 150),
            (198, 40, 40),
            BADGE_OPACITY,
            "×",
        ),
    )


def badge_theme_for_mode(theme_mode: str) -> ThumbnailBadgeTheme:
    """Return badge styles for ``dark`` or ``light``."""
    if theme_mode == "light":
        return badge_theme_light()
    return badge_theme_dark()


def resolve_badge_style_kind(
    *,
    health: ThumbHealth,
    visual: ThumbVisualState | None = None,
    generating: bool = False,
    queued: bool = False,
    decoding: bool = False,
    bridge_error_message: str | None = None,
) -> BadgeStyleKind:
    """Map index + paint state to a badge style family."""
    if decoding or visual == ThumbVisualState.DECODING:
        return BadgeStyleKind.PROGRESS
    if generating or queued or visual == ThumbVisualState.QUEUED:
        return BadgeStyleKind.PROGRESS
    if health == ThumbHealth.HAS_THUMBNAIL or visual == ThumbVisualState.READY:
        return BadgeStyleKind.READY
    if visual == ThumbVisualState.UNSUPPORTED or health == ThumbHealth.UNSUPPORTED:
        return BadgeStyleKind.UNSUPPORTED
    if visual == ThumbVisualState.FAILED or health == ThumbHealth.FAILED_THUMBNAIL:
        if health == ThumbHealth.FAILED_THUMBNAIL:
            if classify_bridge_error_kind(bridge_error_message) == "timeout":
                return BadgeStyleKind.TIMEOUT
            return BadgeStyleKind.FAILED
        return BadgeStyleKind.CORRUPT
    if health == ThumbHealth.MISSING_THUMBNAIL:
        return BadgeStyleKind.INFO
    if visual == ThumbVisualState.PLACEHOLDER:
        return BadgeStyleKind.DEFERRED
    if health == ThumbHealth.PENDING:
        return BadgeStyleKind.DEFERRED
    return BadgeStyleKind.INFO


def gallery_badge_rect(
    thumb_x: int,
    thumb_y: int,
    thumb_w: int,
    thumb_h: int,
    badge_side: int,
    *,
    margin: int = BADGE_MARGIN,
) -> tuple[int, int]:
    """
    Bottom-right badge origin inside a square thumbnail pixmap.

    Returns ``(x, y)`` top-left for the badge pixmap.
    """
    side = max(8, int(badge_side))
    m = max(1, int(margin))
    bx = int(thumb_x) + int(thumb_w) - side - m
    by = int(thumb_y) + int(thumb_h) - side - m
    bx = max(int(thumb_x) + 1, bx)
    by = max(int(thumb_y) + 1, by)
    return bx, by
