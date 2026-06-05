"""Structured metadata diagnostics for support logs (RC3 QoL)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.metadata_display_copy import metadata_unavailable_log_reason

logger = logging.getLogger(__name__)


def log_metadata_snapshot(
    summary: AssetMetadataSummary,
    *,
    size_bytes: int | None = None,
    preview_ready: bool = False,
) -> None:
    """
    Log one JSON line describing metadata availability for *summary*.

    Does not log on every inspector paint — call after scan/render/merge events only.
    """
    try:
        size = int(size_bytes) if size_bytes is not None else None
    except (TypeError, ValueError):
        size = None
    payload = {
        "path": str(summary.path),
        "extension": (summary.ext or "").strip().lower(),
        "size_bytes": size,
        "metadata_source": (summary.metadata_source or "").strip() or "unknown",
        "metadata_status": metadata_unavailable_log_reason(summary),
        "preview_ready": bool(preview_ready),
        "unavailable_reason": metadata_unavailable_log_reason(summary),
        "has_geometry": summary.has_geometry_fields(),
    }
    logger.info("metadata_diagnostics %s", json.dumps(payload, ensure_ascii=False))
