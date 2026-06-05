"""Environment tunables for mesh metadata extraction."""

from __future__ import annotations

import os

_DEFAULT_MAX_INLINE_MB = 100


def max_inline_bytes() -> int:
    """Maximum mesh file size (bytes) for inline geometry extraction."""
    raw = os.environ.get("ROUNDUP_METADATA_MAX_INLINE_MB", str(_DEFAULT_MAX_INLINE_MB))
    try:
        mb = int(raw)
    except (TypeError, ValueError):
        mb = _DEFAULT_MAX_INLINE_MB
    return max(1, mb) * 1024 * 1024


def allow_large_inspector() -> bool:
    """When true, inspector-driven enrichment may parse files above the inline cap."""
    raw = (os.environ.get("ROUNDUP_METADATA_ALLOW_LARGE_INSPECTOR", "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")
