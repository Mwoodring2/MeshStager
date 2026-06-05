"""Prime v1.0 — unified thumbnail presentation (style, placeholders, quality profiles)."""

from meshcorral.ui.thumbnails.thumb_quality_profiles import (
    ThumbQualityProfile,
    default_quality_profile,
    profile_for_name,
)
from meshcorral.ui.thumbnails.badge_paint import build_badge_icon, build_health_badge_icon
from meshcorral.ui.thumbnails.badge_styles import BadgeStyleKind
from meshcorral.ui.thumbnails.thumbnail_confidence import (
    ThumbConfidenceState,
    confidence_state_for,
)
from meshcorral.ui.thumbnails.thumbnail_style_rules import ThumbnailStyleRules, default_style_rules
from meshcorral.ui.thumbnails.unsupported_visuals import (
    UnsupportedVisualKind,
    resolve_unsupported_visual,
)

__all__ = [
    "ThumbConfidenceState",
    "ThumbQualityProfile",
    "ThumbnailStyleRules",
    "UnsupportedVisualKind",
    "BadgeStyleKind",
    "build_badge_icon",
    "build_health_badge_icon",
    "confidence_state_for",
    "default_quality_profile",
    "default_style_rules",
    "profile_for_name",
    "resolve_unsupported_visual",
]
