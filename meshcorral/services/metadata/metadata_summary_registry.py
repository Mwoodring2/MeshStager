"""In-memory registry of :class:`AssetMetadataSummary` by path."""

from __future__ import annotations

import threading
from pathlib import Path

from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.utils.path_utils import safe_resolve_path


class MetadataSummaryRegistry:
    """
    Thread-safe cache of metadata summaries for the working set.

    Populated on the main thread (base fields) and background workers (geometry).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_path: dict[str, AssetMetadataSummary] = {}

    def get(self, path: Path) -> AssetMetadataSummary | None:
        """Return a cached summary or ``None``."""
        key = str(safe_resolve_path(path))
        with self._lock:
            return self._by_path.get(key)

    def put(self, summary: AssetMetadataSummary) -> None:
        """Store or replace a summary."""
        key = str(safe_resolve_path(summary.path))
        with self._lock:
            self._by_path[key] = summary

    def merge(self, summary: AssetMetadataSummary) -> AssetMetadataSummary:
        """Merge with an existing entry, preserving non-None prior geometry when needed."""
        key = str(safe_resolve_path(summary.path))
        with self._lock:
            prior = self._by_path.get(key)
            if prior is None:
                self._by_path[key] = summary
                return summary
            merged = _merge_summaries(prior, summary)
            self._by_path[key] = merged
            return merged

    def clear(self) -> None:
        """Drop all cached summaries (e.g. on new scan)."""
        with self._lock:
            self._by_path.clear()

    def remove_paths_not_in(self, paths: set[str]) -> None:
        """Prune entries not in *paths* (resolved path keys)."""
        with self._lock:
            stale = [k for k in self._by_path if k not in paths]
            for k in stale:
                del self._by_path[k]


def _merge_summaries(
    prior: AssetMetadataSummary,
    new: AssetMetadataSummary,
) -> AssetMetadataSummary:
    """Prefer newly computed geometry; keep archive/thumb fields from either side."""
    return AssetMetadataSummary(
        path=new.path,
        ext=new.ext or prior.ext,
        dimensions_mm=new.dimensions_mm if new.dimensions_mm is not None else prior.dimensions_mm,
        face_count=new.face_count if new.face_count is not None else prior.face_count,
        vertex_count=new.vertex_count if new.vertex_count is not None else prior.vertex_count,
        watertight=new.watertight if new.watertight is not None else prior.watertight,
        mesh_density=new.mesh_density if new.mesh_density is not None else prior.mesh_density,
        archive_member_count=(
            new.archive_member_count
            if new.archive_member_count is not None
            else prior.archive_member_count
        ),
        thumbnail_render_profile=(
            new.thumbnail_render_profile or prior.thumbnail_render_profile
        ),
        metadata_source=new.metadata_source or prior.metadata_source,
        cache_status=new.cache_status or prior.cache_status,
        deferred_reason=new.deferred_reason if new.deferred_reason is not None else prior.deferred_reason,
    )
