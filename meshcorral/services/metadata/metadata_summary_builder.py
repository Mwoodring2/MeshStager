"""Build :class:`AssetMetadataSummary` from records, caches, and optional geometry."""

from __future__ import annotations

import logging
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.services.archive_manifest_cache import ArchiveManifestCache
from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.geometry_metadata import (
    is_mesh_geometry_extension,
    should_defer_geometry,
)

logger = logging.getLogger(__name__)


def archive_member_count_for(
    path: Path,
    archive_cache: ArchiveManifestCache | None,
) -> int | None:
    """Return ZIP member count from manifest cache without extracting."""
    if archive_cache is None:
        return None
    if not ArchiveManifestCache.is_supported_archive(path):
        return None
    try:
        result = archive_cache.ensure_indexed(path)
    except Exception:
        logger.debug("archive manifest lookup failed for %s", path, exc_info=True)
        return None
    if result is None:
        return None
    return int(result.member_count)


def build_base_summary(
    record: FileRecord,
    *,
    archive_cache: ArchiveManifestCache | None = None,
    thumbnail_render_profile: str | None = None,
    thumb_cache_bits: str = "",
) -> AssetMetadataSummary:
    """
    Build a summary without loading mesh geometry (safe on UI thread).

    Geometry fields remain ``None`` until a background pass fills them.
    """
    path = record.path
    ext = record.extension or path.suffix.lower()
    meta_src = record.metadata_source or (
        "stat" if record.is_metadata_enriched() else "pending"
    )
    cache_status = thumb_cache_bits or "pending"
    archive_count = archive_member_count_for(path, archive_cache)

    deferred: str | None = None
    if is_mesh_geometry_extension(ext):
        defer, reason = should_defer_geometry(path, record.size_bytes, allow_large=False)
        if defer:
            deferred = reason
            meta_src = "deferred"
            cache_status = "deferred (size)"

    return AssetMetadataSummary(
        path=path,
        ext=ext,
        archive_member_count=archive_count,
        thumbnail_render_profile=thumbnail_render_profile,
        metadata_source=meta_src,
        cache_status=cache_status,
        deferred_reason=deferred,
    )
