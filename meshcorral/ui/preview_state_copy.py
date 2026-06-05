"""
Canonical preview/thumbnail language for MeshStager (RC3 QoL / Nielsen heuristics).

Use these terms consistently in gallery, inspector, footer, docs, and user-visible logs.
Do not mix deferred / delayed / pending / queued in primary inspector headlines.
"""

from __future__ import annotations

from typing import Final

# --- Preview tiers (footer, inspector tooltips, docs) ---
PREVIEW_CACHED: Final[str] = "Cached Preview"
PREVIEW_PROXY: Final[str] = "Proxy Preview"
PREVIEW_BALANCED: Final[str] = "Balanced Preview"
PREVIEW_HQ: Final[str] = "HQ Preview"

# --- Lifecycle states (cards + inspector headline) ---
PREVIEW_THUMBNAIL_READY: Final[str] = "Thumbnail Ready"
PREVIEW_THUMBNAIL_READY_SUBTITLE: Final[str] = "Preview is available"

PREVIEW_DEFERRED_TITLE: Final[str] = "Deferred Preview"
PREVIEW_DEFERRED_SUBTITLE: Final[str] = (
    "Deferred for speed — preview loads when you browse"
)

PREVIEW_UNSUPPORTED_TITLE: Final[str] = "No Preview"
PREVIEW_UNSUPPORTED_SUBTITLE: Final[str] = (
    "Automatic preview not available for this format"
)

# Short card-face label (format placeholder tile, not inspector headline).
PREVIEW_DEFERRED_CARD_SHORT: Final[str] = "Defer"

# --- System status (footer / status bar); plain English, sentence case where noted ---
STATUS_READY: Final[str] = "Ready"
STATUS_SCANNING_FOLDER: Final[str] = "Scanning folder…"
STATUS_LOADING_THUMBNAILS: Final[str] = "Loading thumbnails…"
STATUS_USING_CACHED_PREVIEWS: Final[str] = "Using cached previews"
STATUS_PROXY_PREVIEW_READY: Final[str] = "Proxy preview ready"
STATUS_BALANCED_PREVIEW_READY: Final[str] = "Balanced preview ready"
STATUS_PREVIEW_QUEUE_COMPLETE: Final[str] = "Preview queue complete"
STATUS_LARGE_FILES_DEFERRED: Final[str] = "Large files deferred for fast browsing"
