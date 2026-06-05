"""Prime v1.0 — user-visible thumbnail confidence / lifecycle states."""

from __future__ import annotations

from enum import Enum

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.asset_state_copy import standard_copy_for_confidence


class ThumbConfidenceState(str, Enum):
    """
    Emotional/readability state for thumbnail tiles (badges and subtitles).

    Distinct from :class:`ThumbHealth` (index truth) and :class:`ThumbVisualState`
    (paint pipeline).
    """

    READY = "ready"
    GENERATING = "generating"
    QUEUED = "queued"
    DECODING = "decoding"
    LOW_CONFIDENCE = "low_confidence"
    FALLBACK = "fallback"
    UNSUPPORTED = "unsupported"
    FAILED = "failed_job"
    CORRUPT = "corrupt"
    TIMEOUT = "timeout"
    DEFERRED = "deferred"
    PENDING = "pending"

    def badge_label(self) -> str:
        """Short overlay/subtitle label."""
        return _BADGE_LABELS[self]

    def card_title(self) -> str:
        """Primary face title on a format card (may override extension identity)."""
        std = standard_copy_for_confidence(self)
        if self in _CARD_OVERRIDE_CONFIDENCE:
            return std.title
        return self.badge_label()

    def card_subtitle(self) -> str:
        """Secondary explanatory line on a format card."""
        return standard_copy_for_confidence(self).subtitle

    def is_failure_family(self) -> bool:
        """True when the state should read as a hard error."""
        return self in (
            ThumbConfidenceState.FAILED,
            ThumbConfidenceState.CORRUPT,
        )

    def is_recoverable_warning(self) -> bool:
        """True when the state is a warning the user can retry (timeout)."""
        return self == ThumbConfidenceState.TIMEOUT

    def is_informational(self) -> bool:
        """True when the state is calm / non-alarming."""
        return self in (
            ThumbConfidenceState.DEFERRED,
            ThumbConfidenceState.UNSUPPORTED,
            ThumbConfidenceState.PENDING,
            ThumbConfidenceState.QUEUED,
            ThumbConfidenceState.GENERATING,
            ThumbConfidenceState.DECODING,
        )


_BADGE_LABELS: dict[ThumbConfidenceState, str] = {
    ThumbConfidenceState.READY: "READY",
    ThumbConfidenceState.GENERATING: "GENERATING",
    ThumbConfidenceState.QUEUED: "QUEUED",
    ThumbConfidenceState.DECODING: "DECODING",
    ThumbConfidenceState.LOW_CONFIDENCE: "LOW",
    ThumbConfidenceState.FALLBACK: "FALLBACK",
    ThumbConfidenceState.UNSUPPORTED: "UNSUPPORTED",
    ThumbConfidenceState.FAILED: "FAILED",
    ThumbConfidenceState.CORRUPT: "CORRUPT",
    ThumbConfidenceState.TIMEOUT: "TIMED OUT",
    ThumbConfidenceState.DEFERRED: "DEFER",
    ThumbConfidenceState.PENDING: "PENDING",
}

_CARD_OVERRIDE_CONFIDENCE: frozenset[ThumbConfidenceState] = frozenset({
    ThumbConfidenceState.DEFERRED,
    ThumbConfidenceState.FAILED,
    ThumbConfidenceState.CORRUPT,
    ThumbConfidenceState.TIMEOUT,
    ThumbConfidenceState.UNSUPPORTED,
})


def confidence_state_for(
    visual: ThumbVisualState,
    *,
    health: ThumbHealth | None = None,
    generating: bool = False,
    low_confidence: bool = False,
    fallback: bool = False,
    deferred: bool = False,
    bridge_error_message: str | None = None,
) -> ThumbConfidenceState:
    """Map paint + health signals to a single confidence label."""
    if deferred or visual == ThumbVisualState.PLACEHOLDER:
        if health == ThumbHealth.UNSUPPORTED:
            return ThumbConfidenceState.UNSUPPORTED
        return ThumbConfidenceState.DEFERRED
    if visual == ThumbVisualState.UNSUPPORTED:
        return ThumbConfidenceState.UNSUPPORTED
    if visual == ThumbVisualState.FAILED:
        if health == ThumbHealth.FAILED_THUMBNAIL:
            from meshcorral.ui.thumbnails.thumbnail_ux_copy import classify_bridge_error_kind

            if classify_bridge_error_kind(bridge_error_message) == "timeout":
                return ThumbConfidenceState.TIMEOUT
            return ThumbConfidenceState.FAILED
        return ThumbConfidenceState.CORRUPT
    if generating or visual == ThumbVisualState.QUEUED:
        return ThumbConfidenceState.GENERATING if generating else ThumbConfidenceState.QUEUED
    if visual == ThumbVisualState.DECODING:
        return ThumbConfidenceState.DECODING
    if low_confidence:
        return ThumbConfidenceState.LOW_CONFIDENCE
    if fallback:
        return ThumbConfidenceState.FALLBACK
    if visual == ThumbVisualState.READY:
        return ThumbConfidenceState.READY
    if health == ThumbHealth.UNSUPPORTED:
        return ThumbConfidenceState.UNSUPPORTED
    return ThumbConfidenceState.PENDING
