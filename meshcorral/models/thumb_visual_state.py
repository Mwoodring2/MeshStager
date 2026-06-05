"""Unified thumbnail presentation state for gallery/table paint (Prime Performance v0.5)."""

from __future__ import annotations

from enum import Enum


class ThumbVisualState(str, Enum):
    """
    Paint-safe visual state for a browse row thumbnail.

    Distinct from :class:`~meshcorral.models.thumb_health.ThumbHealth` (index coverage);
    this tracks what the user sees in the Thumb column / gallery decoration.
    """

    PLACEHOLDER = "placeholder"
    QUEUED = "queued"
    DECODING = "decoding"
    READY = "ready"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"

    def card_label(self) -> str:
        """Short label rendered on format-card placeholders."""
        return _CARD_LABELS[self]


_CARD_LABELS: dict[ThumbVisualState, str] = {
    ThumbVisualState.PLACEHOLDER: "PENDING",
    ThumbVisualState.QUEUED: "QUEUED",
    ThumbVisualState.DECODING: "DECODING",
    ThumbVisualState.READY: "READY",
    ThumbVisualState.UNSUPPORTED: "UNSUPPORTED",
    ThumbVisualState.FAILED: "FAILED",
}
