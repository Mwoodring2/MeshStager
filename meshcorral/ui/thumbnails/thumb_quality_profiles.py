"""Prime v1.0 — thumbnail decode/generation quality profiles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThumbProfileName(str, Enum):
    """Named quality tiers for browse vs inspector vs marketing."""

    DRAFT = "draft"
    STANDARD = "standard"
    HIGH = "high"
    STUDIO = "studio"


@dataclass(frozen=True, slots=True)
class ThumbQualityProfile:
    """
    Parameters that affect perceived thumbnail quality and cost.

    Browse uses *standard*; inspector preview can request *high*.
    """

    name: ThumbProfileName
    display_label: str
    gallery_px: int
    table_px: int
    inspector_preview_px: int
    jpeg_quality: int
    allow_upscale: bool
    exposure_normalize: bool

    def coerce_gallery_px(self, requested: int) -> int:
        """Clamp gallery target size to this profile."""
        return min(max(48, int(requested)), int(self.gallery_px))


_PROFILES: dict[ThumbProfileName, ThumbQualityProfile] = {
    ThumbProfileName.DRAFT: ThumbQualityProfile(
        name=ThumbProfileName.DRAFT,
        display_label="Draft",
        gallery_px=96,
        table_px=48,
        inspector_preview_px=192,
        jpeg_quality=72,
        allow_upscale=False,
        exposure_normalize=False,
    ),
    ThumbProfileName.STANDARD: ThumbQualityProfile(
        name=ThumbProfileName.STANDARD,
        display_label="Standard",
        gallery_px=256,
        table_px=96,
        inspector_preview_px=380,
        jpeg_quality=85,
        allow_upscale=False,
        exposure_normalize=True,
    ),
    ThumbProfileName.HIGH: ThumbQualityProfile(
        name=ThumbProfileName.HIGH,
        display_label="High",
        gallery_px=256,
        table_px=128,
        inspector_preview_px=512,
        jpeg_quality=92,
        allow_upscale=True,
        exposure_normalize=True,
    ),
    ThumbProfileName.STUDIO: ThumbQualityProfile(
        name=ThumbProfileName.STUDIO,
        display_label="Studio",
        gallery_px=512,
        table_px=160,
        inspector_preview_px=768,
        jpeg_quality=95,
        allow_upscale=True,
        exposure_normalize=True,
    ),
}


def default_quality_profile() -> ThumbQualityProfile:
    """Default browse profile (Standard)."""
    return _PROFILES[ThumbProfileName.STANDARD]


def profile_for_name(name: str | ThumbProfileName) -> ThumbQualityProfile:
    """Resolve a profile by enum or string (falls back to standard)."""
    if isinstance(name, ThumbProfileName):
        return _PROFILES[name]
    raw = str(name).strip().lower()
    for key in ThumbProfileName:
        if key.value == raw:
            return _PROFILES[key]
    return default_quality_profile()
