"""Production footer and status-bar copy (Prime v1.0 RC)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from meshcorral.ui.preview_state_copy import (
    PREVIEW_BALANCED,
    PREVIEW_CACHED,
    PREVIEW_HQ,
    PREVIEW_PROXY,
    STATUS_LARGE_FILES_DEFERRED,
    STATUS_LOADING_THUMBNAILS,
    STATUS_PREVIEW_QUEUE_COMPLETE,
    STATUS_BALANCED_PREVIEW_READY,
    STATUS_PROXY_PREVIEW_READY,
    STATUS_READY,
    STATUS_SCANNING_FOLDER,
    STATUS_USING_CACHED_PREVIEWS,
)

# Verbose-only diagnostic keys (logs/Jobs hold full detail).
_VERBOSE_DIAG_KEYS: Final[tuple[str, ...]] = (
    "cache_hits",
    "cache_misses",
    "stale_epoch_drops",
    "bridge_duplicate_skips",
    "bridge_jobs_suppressed",
    "bridge_jobs_pending",
    "bridge_jobs_running",
    "sync_load_attempts_blocked",
    "deferred_decode_requests",
    "evictions",
)

_ENV_VERBOSE_FOOTER: Final[str] = "ROUNDUP_VERBOSE_FOOTER"


def verbose_footer_enabled() -> bool:
    """True when diagnostic counters may appear in the status strip."""
    return os.environ.get(_ENV_VERBOSE_FOOTER, "").strip() == "1"


def _fmt_int(value: int) -> str:
    return f"{max(0, int(value)):,}"


def _join_parts(parts: list[str]) -> str:
    return " · ".join(p for p in parts if p.strip())


@dataclass(frozen=True, slots=True)
class FooterCounts:
    """Indexed / visible / selection counts for the status strip."""

    indexed: int
    visible: int
    selected: int


def format_counts_strip(
    counts: FooterCounts,
    *,
    prime_mode: str | None = None,
    prime_hint: str | None = None,
    filter_note: str | None = None,
    failed_thumbnails: int = 0,
    verbose_diagnostics: str = "",
) -> str:
    """
    Center status strip: file counts and optional Prime / failure hints.

    Queue depth belongs on the thumbnails line, not here.
    """
    parts: list[str] = []
    if prime_mode:
        parts.append(prime_mode.strip())
    parts.append(f"Indexed: {_fmt_int(counts.indexed)}")
    parts.append(f"Visible: {_fmt_int(counts.visible)}")
    parts.append(f"Selected: {_fmt_int(counts.selected)}")
    if failed_thumbnails > 0:
        parts.append(
            f"{failed_thumbnails} thumbnail{'s' if failed_thumbnails != 1 else ''} failed"
        )
        parts.append("Open Jobs for details")
    if prime_hint:
        parts.append(prime_hint.strip())
    if filter_note:
        parts.append(filter_note.strip())
    if verbose_diagnostics.strip():
        parts.append(verbose_diagnostics.strip())
    return _join_parts(parts)


def format_footer_confidence_counts(
    indexed: int,
    visible: int,
    selected: int,
    queue_pending: int,
) -> str:
    """
    Legacy formatter (tests and callers).

    *queue_pending* is ignored in production layout; queue depth is shown on the
    thumbnails permanent widget instead.
    """
    _ = queue_pending
    return format_counts_strip(FooterCounts(indexed, visible, selected))


def prime_mode_label(*, prime_active: bool, network_like: bool) -> str | None:
    """Return ``Prime Local`` / ``Prime Server`` when performance mode is active."""
    if not prime_active:
        return None
    return "Prime Server" if network_like else "Prime Local"


def prime_mode_hint(*, prime_active: bool, network_like: bool) -> str | None:
    """Short Prime hint for the counts strip after scan or while browsing."""
    if not prime_active:
        return None
    if network_like:
        return "Visible previews load first on server folders"
    return f"{STATUS_USING_CACHED_PREVIEWS} when available"


def format_workflow_status(
    state: str,
    *,
    detail: str = "",
) -> str:
    """Primary (left) status label: Ready, Scanning…, Searching…, etc."""
    base = (state or STATUS_READY).strip()
    if detail.strip():
        return f"{base} · {detail.strip()}"
    return base


def format_app_footer(
    *,
    workflow: str,
    counts: FooterCounts,
    prime_mode: str | None = None,
    prime_hint: str | None = None,
    filter_note: str | None = None,
    failed_thumbnails: int = 0,
    verbose_diagnostics: str = "",
) -> str:
    """Compose workflow + counts for a single-line footer (optional tooling)."""
    return _join_parts(
        [
            workflow,
            format_counts_strip(
                counts,
                prime_mode=prime_mode,
                prime_hint=prime_hint,
                filter_note=filter_note,
                failed_thumbnails=failed_thumbnails,
                verbose_diagnostics=verbose_diagnostics,
            ),
        ]
    )


def format_thumbnail_footer(
    *,
    generating: int = 0,
    queued: int = 0,
    decoding: int = 0,
    batch_completed: int = 0,
    batch_total: int = 0,
) -> str:
    """Permanent thumbnails widget: compact activity summary."""
    if batch_total > 0 and batch_completed < batch_total:
        return f"Thumbnails: Generating {batch_completed} of {batch_total}"
    parts: list[str] = []
    if generating > 0:
        parts.append(f"Generating {generating}")
    if queued > 0:
        parts.append(f"Queued {queued}")
    if decoding > 0:
        parts.append(f"Loading {decoding} preview{'s' if decoding != 1 else ''}")
    if parts:
        return "Thumbnails: " + " · ".join(parts)
    return "Thumbnails: Ready"


def format_thumbnail_failure_footer(
    *,
    source_filename: str,
    error_message: str | None = None,
) -> str:
    """One-shot status toast when a thumbnail job fails."""
    _ = error_message
    name = (source_filename or "").strip() or "this file"
    return f"Thumbnail failed for {name}. Open Jobs for details."


def format_thumbnail_failures_summary(*, failed_count: int) -> str:
    """Aggregate failure hint when multiple thumbnails failed."""
    n = max(0, int(failed_count))
    if n <= 0:
        return ""
    word = "thumbnail" if n == 1 else "thumbnails"
    return f"{n} {word} failed · Open Jobs for details"


def format_scan_footer(
    *,
    files_found: int,
    folder_hint: str = "",
    esc_hint: bool = True,
) -> str:
    """Status while a folder scan is walking the tree."""
    base = f"{STATUS_SCANNING_FOLDER} {_fmt_int(files_found)} files found"
    parts: list[str] = [base]
    if folder_hint.strip():
        parts.append(folder_hint.strip())
    if esc_hint:
        parts.append("Press Esc to cancel")
    return " · ".join(parts)


def format_scan_still_scanning_footer(*, files_found: int) -> str:
    """Status when the walk continues but matched-file count has not changed recently."""
    return (
        f"Still scanning… {_fmt_int(files_found)} files found · Press Esc to cancel"
    )


def format_loading_thumbnails_progress(*, completed: int, total: int) -> str:
    """Primary status while post-scan thumbnail batches are in flight."""
    return f"{STATUS_LOADING_THUMBNAILS} {_fmt_int(completed)} / {_fmt_int(total)}"


def format_scan_cancel_pending_footer() -> str:
    """Status while a cooperative scan cancel is in flight."""
    return "Canceling scan…"


def status_canceling_scan() -> str:
    """One-shot status bar message when the user requests scan cancel."""
    return "Canceling scan…"


def format_scan_complete_message(
    *,
    record_count: int,
    from_cache_hits: int = 0,
    network_like: bool = False,
) -> str:
    """Calm post-scan ready message (not cache diagnostics)."""
    if record_count <= 0:
        return STATUS_READY
    if from_cache_hits > 0 and network_like:
        return f"Ready · {_fmt_int(record_count)} assets · metadata from cache"
    return f"Ready · {_fmt_int(record_count)} assets indexed"


def format_filter_footer(
    *,
    visible: int,
    indexed: int,
    query: str = "",
) -> tuple[str, str]:
    """
    Return (workflow_label, counts_suffix) after a filter pass.

    *workflow_label* goes on the primary status widget; *counts_suffix* may be
    merged into the counts strip by the caller when needed.
    """
    if query.strip():
        workflow = "Searching…"
        suffix = f"Query: {query.strip()}"
        return workflow, suffix
    if indexed > 0 and visible < indexed:
        return "Filtered", f"{_fmt_int(visible)} visible of {_fmt_int(indexed)}"
    return "Filtered", ""


def format_bridge_footer(
    *,
    readiness: str,
    job_state: str | None = None,
    job_detail: str = "",
) -> str:
    """
    Permanent Bridge line (path readiness or transient job state).

    *readiness* is typically Ready / Not configured / Not found from path discovery.
    """
    if job_state and job_state.strip() and job_state.strip().lower() != "idle":
        state = job_state.strip()
        if job_detail.strip():
            return f"Bridge: {state} · {job_detail.strip()}"
        return f"Bridge: {state}"
    ready = (readiness or "Not configured").strip()
    return f"Bridge: {ready}"


def format_selection_footer(*, selected: int, visible: int) -> str:
    """Short selection summary for optional toasts."""
    if selected <= 0:
        return "No selection"
    if selected == 1:
        return "1 selected"
    return f"{selected:,} selected of {_fmt_int(visible)} visible"


def format_verbose_diagnostics(snapshot: dict[str, int | float]) -> str:
    """Compact diagnostic suffix for ``ROUNDUP_VERBOSE_FOOTER=1`` only."""
    parts: list[str] = []
    for key in _VERBOSE_DIAG_KEYS:
        if key not in snapshot:
            continue
        val = snapshot[key]
        if isinstance(val, float):
            parts.append(f"{key}={val:.1f}")
        else:
            parts.append(f"{key}={val}")
    return _join_parts(parts)


# --- One-shot status toasts (statusBar().showMessage) ---


def status_scan_canceled() -> str:
    return "Scan canceled."


def status_source_unavailable() -> str:
    return "Source unavailable."


def status_no_matching_results() -> str:
    return "No matching results."


def status_generating_visible_thumbnails() -> str:
    return "Generating visible previews…"


def status_thumbnails_deferred() -> str:
    return STATUS_LARGE_FILES_DEFERRED


def status_preview_queue_complete() -> str:
    return STATUS_PREVIEW_QUEUE_COMPLETE


def status_loading_thumbnails() -> str:
    return STATUS_LOADING_THUMBNAILS


def status_using_cached_previews() -> str:
    return STATUS_USING_CACHED_PREVIEWS


def status_balanced_preview_ready() -> str:
    return STATUS_BALANCED_PREVIEW_READY


def status_proxy_preview_ready() -> str:
    return STATUS_PROXY_PREVIEW_READY


def status_ready() -> str:
    return STATUS_READY


def friendly_render_pipeline_status(message: str) -> str:
    """Plain-English footer text for mesh render pipeline status (display only)."""
    key = (message or "").strip()
    friendly = {
        "Copying from server": "Copying from server…",
        "Loading mesh": "Loading mesh…",
        "Computing geometry": f"Preparing {PREVIEW_BALANCED}…",
        "Rendering preview": f"Rendering {PREVIEW_PROXY}…",
        "Rendering proxy preview": f"Rendering {PREVIEW_PROXY}…",
        "Rendering balanced preview": f"Rendering {PREVIEW_BALANCED}…",
        "Rendering HQ preview": f"Rendering {PREVIEW_HQ}…",
        "Using cached preview": STATUS_USING_CACHED_PREVIEWS,
        "Saving preview cache": STATUS_BALANCED_PREVIEW_READY,
        "Saving proxy preview cache": STATUS_PROXY_PREVIEW_READY,
        "Saving balanced preview cache": STATUS_BALANCED_PREVIEW_READY,
    }
    return friendly.get(key, key)


def meshstager_log_dir_hint() -> str:
    """One-line hint for where MeshStager writes logs (tester docs / about)."""
    return r"%LOCALAPPDATA%\MeshStager\logs"


def status_layout_saved(name: str) -> str:
    label = (name or "").strip()
    if label:
        return f"Layout saved: {label}"
    return "Layout saved."


def status_layout_loaded(name: str) -> str:
    label = (name or "").strip()
    if label:
        return f"Layout loaded: {label}"
    return "Layout loaded."


def status_layout_reset() -> str:
    return "Layout reset to defaults."


def status_preset_applied(name: str) -> str:
    return f"Preset applied: {name}"


def status_settings_saved() -> str:
    return "Settings saved."


def status_export_complete() -> str:
    return "Export complete."


def status_native_thumbnails_blender_fallback() -> str:
    return "Native thumbnails unavailable · Using slower fallback path"


def status_scrolling_thumbnails_paused() -> str:
    return "Scrolling — previews paused briefly"


def status_loading_visible_thumbnails() -> str:
    return "Loading visible previews…"


def status_scan_folder_first() -> str:
    return "Scan a folder first."


def status_metadata_copied() -> str:
    return "Metadata copied to the clipboard."


def status_path_copied() -> str:
    return "Path copied to the clipboard."


def status_thumbnail_ready(filename: str) -> str:
    from meshcorral.ui.preview_state_copy import PREVIEW_THUMBNAIL_READY

    name = (filename or "").strip() or "thumbnail"
    return f"{PREVIEW_THUMBNAIL_READY} · {name}"
