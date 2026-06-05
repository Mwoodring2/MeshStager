"""
Policy for Fast Proxy vs Balanced Preview vs HQ Preview mesh rendering.

Preview quality must support asset identification — speed wins only when the
thumbnail still helps confirm the correct mesh. See
``docs/RC3_THUMBNAIL_QUALITY_REGRESSION.md`` and
``docs/MESHSTAGER_UI_UX_GUIDE.md``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# Files at or above this size use proxy preview unless HQ is requested.
LARGE_MESH_PROXY_BYTES: int = int(
    os.environ.get("MESHSTAGER_PROXY_THRESHOLD_MB", "48").strip() or "48"
) * (1024 * 1024)

# Small local files get full balanced surface quality.
SMALL_FILE_BALANCED_BYTES: int = int(
    os.environ.get("MESHSTAGER_BALANCED_SMALL_MB", "8").strip() or "8"
) * (1024 * 1024)

PROXY_MAX_PX: int = int(os.environ.get("MESHSTAGER_PROXY_MAX_PX", "192").strip() or "192")
PROXY_MAX_POINTS: int = int(os.environ.get("MESHSTAGER_PROXY_MAX_POINTS", "18000").strip() or "18000")
BALANCED_MAX_PX: int = int(os.environ.get("MESHSTAGER_BALANCED_MAX_PX", "384").strip() or "384")
BALANCED_MAX_POINTS: int = int(
    os.environ.get("MESHSTAGER_BALANCED_MAX_POINTS", "60000").strip() or "60000"
)
BALANCED_SMALL_MAX_FACES: int = int(
    os.environ.get("MESHSTAGER_BALANCED_SMALL_MAX_FACES", "14000").strip() or "14000"
)
BALANCED_MEDIUM_MAX_FACES: int = int(
    os.environ.get("MESHSTAGER_BALANCED_MEDIUM_MAX_FACES", "8000").strip() or "8000"
)
HQ_MAX_FACES: int = int(os.environ.get("MESHSTAGER_HQ_MAX_FACES", "22000").strip() or "22000")

# Internal quality modes (``render_mode`` in cache keys and timing logs).
QUALITY_FAST_PROXY: Final[str] = "proxy"
QUALITY_BALANCED_PREVIEW: Final[str] = "balanced"
QUALITY_HQ_PREVIEW: Final[str] = "high"

ALL_QUALITY_MODES: Final[frozenset[str]] = frozenset(
    {
        QUALITY_FAST_PROXY,
        QUALITY_BALANCED_PREVIEW,
        QUALITY_HQ_PREVIEW,
    }
)


def quality_mode_display_label(render_mode: str) -> str:
    """Return the locked user-facing label for a render_mode value."""
    from meshcorral.ui.preview_state_copy import (
        PREVIEW_BALANCED,
        PREVIEW_HQ,
        PREVIEW_PROXY,
    )

    mode = (render_mode or QUALITY_BALANCED_PREVIEW).strip().lower()
    if mode == QUALITY_FAST_PROXY:
        return PREVIEW_PROXY
    if mode == QUALITY_HQ_PREVIEW:
        return PREVIEW_HQ
    return PREVIEW_BALANCED


def file_size_bytes(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def resolve_render_mode(
    path: Path,
    *,
    size_bytes: int,
    high_quality: bool,
    for_auto_enqueue: bool,
) -> str:
    """
    Return render mode: ``proxy`` | ``balanced`` | ``high``.

    HQ runs only when *high_quality* is True (manual regenerate).
    Large files use Fast Proxy first; better preview is on demand (HQ).
    Small/medium local and network files default to Balanced Preview
    (professional shaded surface for small files via higher face budget).
    Network paths are staged safely but are not permanently downgraded to proxy.
    Bulk auto-enqueue uses the same tier rules; gallery deferral is handled separately.
    """
    if high_quality:
        return QUALITY_HQ_PREVIEW
    if size_bytes >= LARGE_MESH_PROXY_BYTES:
        return QUALITY_FAST_PROXY
    return QUALITY_BALANCED_PREVIEW


def effective_max_px(render_mode: str, requested_max_px: int) -> int:
    """Clamp output pixels by render mode."""
    px = int(requested_max_px)
    mode = (render_mode or "balanced").strip().lower()
    if mode == "proxy":
        return max(64, min(PROXY_MAX_PX, px))
    if mode == "balanced":
        return max(96, min(BALANCED_MAX_PX, px))
    return max(96, min(512, px))


def effective_max_points(render_mode: str) -> int:
    """Vertex sample budget for splat fallback / proxy."""
    mode = (render_mode or "balanced").strip().lower()
    if mode == "proxy":
        return PROXY_MAX_POINTS
    if mode == "balanced":
        return BALANCED_MAX_POINTS
    raw = os.environ.get("ROUNDUP_NATIVE_THUMB_MAX_POINTS", "60000").strip() or "60000"
    try:
        return max(1000, int(raw))
    except ValueError:
        return 60000


def effective_max_faces(render_mode: str, *, size_bytes: int) -> int:
    """Triangle budget for balanced/HQ surface raster."""
    mode = (render_mode or "balanced").strip().lower()
    if mode == "high":
        return HQ_MAX_FACES
    if mode == "balanced":
        if size_bytes < SMALL_FILE_BALANCED_BYTES:
            return BALANCED_SMALL_MAX_FACES
        return BALANCED_MEDIUM_MAX_FACES
    return max(2000, BALANCED_MEDIUM_MAX_FACES // 2)
