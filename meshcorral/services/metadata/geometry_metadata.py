"""Cheap STL/OBJ geometry stats (background-only; never call from UI thread)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.metadata_tunables import allow_large_inspector, max_inline_bytes

logger = logging.getLogger(__name__)

MESH_GEOMETRY_EXTENSIONS: frozenset[str] = frozenset({".stl", ".obj"})

_STATUS_DEFERRED = "deferred"
_STATUS_LIVE = "live"
_STATUS_RENDER = "render"
_STATUS_UNAVAILABLE = "unavailable"


def is_mesh_geometry_extension(ext: str) -> bool:
    """True when inline geometry extraction applies to this extension."""
    normalized = ext.lower().strip()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized in MESH_GEOMETRY_EXTENSIONS


def should_defer_geometry(
    path: Path,
    size_bytes: int | None,
    *,
    allow_large: bool = False,
) -> tuple[bool, str | None]:
    """
    Return whether extraction should be deferred for size policy.

    *allow_large* is set when the inspector explicitly requests enrichment.
    """
    if size_bytes is None:
        try:
            size_bytes = path.stat().st_size
        except OSError:
            return False, None
    limit = max_inline_bytes()
    if size_bytes <= limit:
        return False, None
    if allow_large and allow_large_inspector():
        return False, None
    mb = max(1, limit // (1024 * 1024))
    return True, f"File exceeds {mb} MB inline metadata cap"


def extract_geometry_metadata(
    path: Path,
    *,
    size_bytes: int | None = None,
    allow_large: bool = False,
) -> AssetMetadataSummary:
    """
    Extract mesh statistics for STL/OBJ.

    Intended for worker threads only. Returns partial summaries with deferral
    markers when parsing is skipped.
    """
    ext = path.suffix.lower()
    base = AssetMetadataSummary(path=path, ext=ext)

    if not is_mesh_geometry_extension(ext):
        return base.with_updates(
            metadata_source=_STATUS_UNAVAILABLE,
            cache_status="not a mesh geometry file",
        )

    defer, reason = should_defer_geometry(path, size_bytes, allow_large=allow_large)
    if defer:
        return base.with_updates(
            metadata_source=_STATUS_DEFERRED,
            cache_status="deferred",
            deferred_reason=reason,
        )

    try:
        if not path.is_file():
            return base.with_updates(
                metadata_source=_STATUS_UNAVAILABLE,
                cache_status="missing file",
            )
    except OSError as exc:
        return base.with_updates(
            metadata_source=_STATUS_UNAVAILABLE,
            cache_status=str(exc),
        )

    try:
        import trimesh  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("trimesh not available for geometry metadata")
        return base.with_updates(
            metadata_source=_STATUS_UNAVAILABLE,
            cache_status="trimesh not installed",
            deferred_reason="Install trimesh for mesh stats",
        )

    try:
        loaded = trimesh.load(
            str(path),
            force="mesh",
            skip_materials=True,
            process=False,
        )
    except Exception as exc:
        logger.debug("geometry load failed for %s: %s", path, exc)
        return base.with_updates(
            metadata_source=_STATUS_UNAVAILABLE,
            cache_status="parse failed",
            deferred_reason=str(exc),
        )

    mesh = _coalesce_trimesh(loaded)
    if mesh is None:
        return base.with_updates(
            metadata_source=_STATUS_UNAVAILABLE,
            cache_status="scene not supported",
        )

    return summary_from_loaded_mesh(
        path,
        mesh,
        metadata_source=_STATUS_LIVE,
        cache_status="live",
    )


def _coalesce_trimesh(loaded: Any) -> Any | None:
    """Return a single mesh object from a trimesh load result."""
    mesh = loaded
    if hasattr(loaded, "dump") and not hasattr(loaded, "vertices"):
        try:
            mesh = loaded.dump(concatenate=True)  # type: ignore[assignment]
        except Exception:
            return None
    return mesh


def summary_from_loaded_mesh(
    path: Path,
    mesh: Any,
    *,
    metadata_source: str = _STATUS_RENDER,
    cache_status: str = "render",
) -> AssetMetadataSummary:
    """
    Build an :class:`AssetMetadataSummary` from an already-loaded mesh.

    Safe on worker threads when the mesh was loaded for preview/render.
    """
    ext = path.suffix.lower()
    base = AssetMetadataSummary(path=path, ext=ext)
    vertices = getattr(mesh, "vertices", None)
    faces = getattr(mesh, "faces", None)
    if vertices is None or len(vertices) == 0:
        return base.with_updates(
            metadata_source=_STATUS_UNAVAILABLE,
            cache_status="no vertices",
        )

    vertex_count = int(len(vertices))
    face_count = int(len(faces)) if faces is not None else None

    bounds = getattr(mesh, "bounds", None)
    dimensions_mm: tuple[float, float, float] | None = None
    mesh_density: float | None = None
    if bounds is not None and len(bounds) >= 2:
        extents = bounds[1] - bounds[0]
        dimensions_mm = (float(extents[0]), float(extents[1]), float(extents[2]))
        volume = float(extents[0] * extents[1] * extents[2])
        if face_count is not None and volume > 1e-9:
            mesh_density = float(face_count) / volume

    watertight: bool | None = None
    is_wt = getattr(mesh, "is_watertight", None)
    if is_wt is not None:
        try:
            watertight = bool(is_wt() if callable(is_wt) else is_wt)
        except Exception:
            watertight = None

    return base.with_updates(
        dimensions_mm=dimensions_mm,
        face_count=face_count,
        vertex_count=vertex_count,
        watertight=watertight,
        mesh_density=mesh_density,
        metadata_source=metadata_source,
        cache_status=cache_status,
        deferred_reason=None,
    )
