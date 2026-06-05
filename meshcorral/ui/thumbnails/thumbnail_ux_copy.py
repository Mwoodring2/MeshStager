"""Production-facing copy for thumbnail lifecycle and failures (Prime v1.0 RC)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.asset_state_copy import (
    STATE_CORRUPT,
    STATE_DEFERRED,
    STATE_FAILED,
    STATE_READY,
    STATE_TIMEOUT,
    STATE_UNSUPPORTED,
    standard_copy_for_inspector,
)

BridgeErrorKind = Literal["failed", "timeout", "corrupt"]

# --- Plain-English reasons (non-ready states) ---
REASON_UNSUPPORTED = (
    "This file type does not support automatic thumbnails yet."
)
REASON_DEFERRED_PERF = (
    "MeshStager queues this preview so browsing large folders stays responsive."
)
REASON_FAILED_GENERIC = (
    "MeshStager could not generate a thumbnail for this file."
)
REASON_CORRUPT = (
    "The file may be empty, malformed, or unreadable."
)
REASON_TIMEOUT = (
    "Thumbnail generation took too long and was stopped."
)
REASON_PENDING = "Thumbnail has not been generated yet."

# --- Short status titles (Preview / badges; align with asset_state_copy) ---
TITLE_READY = STATE_READY.title
TITLE_GENERATING = "Generating"
TITLE_QUEUED = "Queued"
TITLE_DECODING = "Loading"
TITLE_DEFERRED = STATE_DEFERRED.title
TITLE_UNSUPPORTED = STATE_UNSUPPORTED.title
TITLE_FAILED = STATE_FAILED.title
TITLE_CORRUPT = STATE_CORRUPT.title
TITLE_TIMEOUT = STATE_TIMEOUT.title
TITLE_PENDING = "Pending"


def classify_bridge_error_kind(message: str | None) -> BridgeErrorKind:
    """Classify a bridge/native error string for user-facing copy (best-effort)."""
    m = (message or "").strip().lower()
    if not m:
        return "failed"
    if "timeout" in m or "timed out" in m or "time out" in m:
        return "timeout"
    for token in (
        "empty mesh",
        "no vertices",
        "invalid stl",
        "invalid obj",
        "corrupt",
        "malformed",
        "unreadable",
        "truncated",
        "unexpected eof",
        "bad mesh",
        "decode error",
    ):
        if token in m:
            return "corrupt"
    return "failed"


def reason_for_bridge_error_kind(kind: BridgeErrorKind) -> str:
    """User-facing reason line for a classified bridge/native failure."""
    if kind == "timeout":
        return REASON_TIMEOUT
    if kind == "corrupt":
        return REASON_CORRUPT
    return REASON_FAILED_GENERIC


def suggested_action_for_preview(
    *,
    health: ThumbHealth,
    visual: ThumbVisualState,
    can_mesh_thumbnail: bool,
    has_thumbnail: bool,
    thumb_perf_deferred: bool,
    failure_kind: BridgeErrorKind | None,
) -> str:
    """One-line suggestion for Diagnostics / inspector."""
    if health == ThumbHealth.UNSUPPORTED or visual == ThumbVisualState.UNSUPPORTED:
        return "No automatic thumbnail is available for this format."
    if not can_mesh_thumbnail:
        if health == ThumbHealth.HAS_THUMBNAIL or has_thumbnail:
            return "Preview should load when you select the file."
        return "Use Open file or an external viewer for this asset."
    if thumb_perf_deferred or visual == ThumbVisualState.PLACEHOLDER:
        if health == ThumbHealth.PENDING and not has_thumbnail:
            return "Scroll slowly or pause; thumbnails load as rows become ready."
    if health == ThumbHealth.FAILED_THUMBNAIL or visual == ThumbVisualState.FAILED:
        if failure_kind == "timeout":
            return "Try again, or open Jobs for logs and output."
        if failure_kind == "corrupt":
            return "Verify the file opens in a mesh viewer, then try again."
        return "Try again, or open Jobs for logs and output."
    if health == ThumbHealth.MISSING_THUMBNAIL:
        return "Use Generate / Retry thumbnail to queue a render."
    if health == ThumbHealth.HAS_THUMBNAIL and not has_thumbnail:
        return "Wait for the preview decode to finish."
    return "If this persists, open Jobs for details."


def infer_thumbnail_backend_label(renderer_profile_display: str) -> str:
    """Short backend label from render profile text (no new pipeline signals)."""
    s = (renderer_profile_display or "").strip().lower()
    if not s or s == "—":
        return "Not available"
    if "blender" in s:
        return "Blender bridge"
    if "native" in s or "cpu" in s or "local" in s:
        return "Local (native)"
    return "Automatic (policy)"


@dataclass(frozen=True, slots=True)
class PreviewThumbUx:
    """Strings and affordances for the inspector Preview tab."""

    headline: str
    body: str
    show_retry: bool
    retry_button_label: str


def build_preview_thumb_ux(
    *,
    health: ThumbHealth,
    visual: ThumbVisualState,
    generating: bool,
    queued: bool,
    decoding: bool,
    can_mesh_thumbnail: bool,
    has_blender_thumbnail: bool,
    bridge_error_message: str | None,
    thumb_perf_deferred: bool,
) -> PreviewThumbUx:
    """
    Map index + paint state to preview copy and retry visibility.

    *generating* / *queued* / *decoding* come from the live controller (caller).
    """
    std = standard_copy_for_inspector(
        health=health,
        visual=visual,
        generating=generating,
        queued=queued,
        decoding=decoding,
        deferred=thumb_perf_deferred and visual == ThumbVisualState.PLACEHOLDER,
        bridge_error_message=bridge_error_message,
    )
    show_retry = bool(can_mesh_thumbnail)
    if health == ThumbHealth.UNSUPPORTED or visual == ThumbVisualState.UNSUPPORTED:
        return PreviewThumbUx(
            headline=std.title,
            body=std.subtitle,
            show_retry=False,
            retry_button_label="Retry thumbnail",
        )
    if decoding or generating or queued:
        return PreviewThumbUx(
            headline=std.title,
            body=std.subtitle,
            show_retry=show_retry,
            retry_button_label="Retry thumbnail",
        )
    if std.title in (STATE_FAILED.title, STATE_TIMEOUT.title, STATE_CORRUPT.title):
        return PreviewThumbUx(
            headline=std.title,
            body=std.subtitle,
            show_retry=show_retry,
            retry_button_label="Retry thumbnail",
        )
    if std.title == STATE_READY.title:
        return PreviewThumbUx(
            headline=std.title,
            body=std.subtitle,
            show_retry=False,
            retry_button_label="Regenerate thumbnail",
        )
    if std.title == STATE_DEFERRED.title:
        return PreviewThumbUx(
            headline=std.title,
            body=std.subtitle,
            show_retry=show_retry,
            retry_button_label="Retry thumbnail",
        )
    return PreviewThumbUx(
        headline=std.title,
        body=std.subtitle,
        show_retry=show_retry,
        retry_button_label="Generate thumbnail",
    )


def format_thumbnail_failure_footer_concise(*, source_filename: str) -> str:
    """Single-line footer for a failed thumbnail job (production tone)."""
    name = (source_filename or "").strip() or "this file"
    return f"Thumbnail failed for {name}. Open Jobs for details."
