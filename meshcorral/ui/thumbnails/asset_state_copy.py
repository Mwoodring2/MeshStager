"""Prime v1.0 RC — standard asset/thumbnail state language (gallery, table, inspector)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.preview_state_copy import (
    PREVIEW_DEFERRED_SUBTITLE,
    PREVIEW_DEFERRED_TITLE,
    PREVIEW_THUMBNAIL_READY,
    PREVIEW_THUMBNAIL_READY_SUBTITLE,
    PREVIEW_UNSUPPORTED_SUBTITLE,
    PREVIEW_UNSUPPORTED_TITLE,
)

if TYPE_CHECKING:
    from meshcorral.ui.thumbnails.thumbnail_confidence import ThumbConfidenceState


@dataclass(frozen=True, slots=True)
class StandardAssetStateCopy:
    """Primary title + secondary subtitle shown on cards and inspector preview."""

    title: str
    subtitle: str


# Canonical lifecycle copy (A5.3) — titles from :mod:`preview_state_copy`.
STATE_READY = StandardAssetStateCopy(
    PREVIEW_THUMBNAIL_READY,
    PREVIEW_THUMBNAIL_READY_SUBTITLE,
)
STATE_DEFERRED = StandardAssetStateCopy(
    PREVIEW_DEFERRED_TITLE,
    PREVIEW_DEFERRED_SUBTITLE,
)
STATE_UNSUPPORTED = StandardAssetStateCopy(
    PREVIEW_UNSUPPORTED_TITLE,
    PREVIEW_UNSUPPORTED_SUBTITLE,
)
STATE_FAILED = StandardAssetStateCopy("Failed", "Thumbnail generation failed")
STATE_TIMEOUT = StandardAssetStateCopy("Timed Out", "Try generating again")
STATE_CORRUPT = StandardAssetStateCopy("Corrupt", "File may be unreadable")

# In-flight pipeline states (operational, not lifecycle failures).
STATE_GENERATING = StandardAssetStateCopy("Generating", "Thumbnail job running")
STATE_QUEUED = StandardAssetStateCopy("Queued", "Waiting in thumbnail queue")
STATE_DECODING = StandardAssetStateCopy("Loading preview", "Loading preview image")
STATE_PENDING = StandardAssetStateCopy("Pending", "Thumbnail not generated yet")

_CONFIDENCE_TABLE: dict[object, StandardAssetStateCopy] | None = None


def _confidence_copy_table() -> dict[object, StandardAssetStateCopy]:
    """Lazy table to avoid import cycles with :mod:`thumbnail_confidence`."""
    global _CONFIDENCE_TABLE
    if _CONFIDENCE_TABLE is not None:
        return _CONFIDENCE_TABLE
    from meshcorral.ui.thumbnails.thumbnail_confidence import ThumbConfidenceState

    _CONFIDENCE_TABLE = {
        ThumbConfidenceState.READY: STATE_READY,
        ThumbConfidenceState.GENERATING: STATE_GENERATING,
        ThumbConfidenceState.QUEUED: STATE_QUEUED,
        ThumbConfidenceState.DECODING: STATE_DECODING,
        ThumbConfidenceState.LOW_CONFIDENCE: StandardAssetStateCopy(
            "Low confidence", "Review thumbnail"
        ),
        ThumbConfidenceState.FALLBACK: StandardAssetStateCopy("Fallback", "Blender fallback"),
        ThumbConfidenceState.UNSUPPORTED: STATE_UNSUPPORTED,
        ThumbConfidenceState.FAILED: STATE_FAILED,
        ThumbConfidenceState.CORRUPT: STATE_CORRUPT,
        ThumbConfidenceState.TIMEOUT: STATE_TIMEOUT,
        ThumbConfidenceState.DEFERRED: STATE_DEFERRED,
        ThumbConfidenceState.PENDING: STATE_PENDING,
    }
    return _CONFIDENCE_TABLE


def standard_copy_for_confidence(state: ThumbConfidenceState) -> StandardAssetStateCopy:
    """Map a confidence enum to the standard title/subtitle pair."""
    return _confidence_copy_table()[state]


def standard_copy_for_inspector(
    *,
    health: ThumbHealth,
    visual: ThumbVisualState,
    generating: bool = False,
    queued: bool = False,
    decoding: bool = False,
    deferred: bool = False,
    bridge_error_message: str | None = None,
) -> StandardAssetStateCopy:
    """
    Resolve the standard user-facing state for gallery/table/inspector surfaces.

    Technical reasons (size caps, bridge logs) belong in Diagnostics only.
    """
    if decoding:
        return STATE_DECODING
    if generating:
        return STATE_GENERATING
    if queued:
        return STATE_QUEUED
    from meshcorral.ui.thumbnails.thumbnail_confidence import confidence_state_for

    conf = confidence_state_for(
        visual,
        health=health,
        generating=generating,
        deferred=deferred,
        bridge_error_message=bridge_error_message,
    )
    return standard_copy_for_confidence(conf)
