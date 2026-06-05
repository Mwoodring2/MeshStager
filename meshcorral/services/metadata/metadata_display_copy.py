"""Plain-English metadata status and field placeholders (RC3 QoL)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary

METADATA_STATUS_READY: str = "Ready"
METADATA_STATUS_PENDING: str = "Metadata pending"
METADATA_STATUS_DEFERRED: str = "Deferred for speed"
METADATA_STATUS_UNAVAILABLE: str = "Metadata unavailable"
METADATA_STATUS_UNSUPPORTED: str = "Unsupported file type"
METADATA_STATUS_NOT_LOADED: str = "Not loaded yet"
METADATA_PREVIEW_READY_NOT_LOADED: str = "Preview ready, metadata not loaded"

FIELD_PENDING: str = METADATA_STATUS_PENDING
FIELD_DEFERRED: str = METADATA_STATUS_DEFERRED
FIELD_UNAVAILABLE: str = METADATA_STATUS_UNAVAILABLE
FIELD_UNSUPPORTED: str = METADATA_STATUS_UNSUPPORTED
FIELD_NOT_LOADED: str = METADATA_STATUS_NOT_LOADED


def metadata_status_label(summary: "AssetMetadataSummary") -> str:
    """High-level metadata readiness separate from thumbnail/preview state."""
    from meshcorral.services.metadata.geometry_metadata import is_mesh_geometry_extension

    ext = (summary.ext or "").strip().lower()
    if not is_mesh_geometry_extension(ext):
        if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".tga", ".bmp", ".webp", ".exr", ".hdr", ".psd"):
            return METADATA_STATUS_READY
        if ext in (".zip", ".7z", ".rar"):
            return METADATA_STATUS_READY if summary.archive_member_count is not None else METADATA_STATUS_PENDING
        return METADATA_STATUS_UNSUPPORTED

    if summary.has_geometry_fields():
        src = (summary.metadata_source or "").strip().lower()
        if src in ("live", "render", "stat", "scan"):
            return METADATA_STATUS_READY
        return METADATA_STATUS_READY

    deferred = (summary.deferred_reason or "").strip()
    if deferred:
        return METADATA_STATUS_DEFERRED

    src = (summary.metadata_source or "").strip().lower()
    if src == "deferred":
        return METADATA_STATUS_DEFERRED
    if src == "unavailable":
        return METADATA_STATUS_UNAVAILABLE
    if src in ("pending", ""):
        return METADATA_STATUS_PENDING
    return METADATA_STATUS_NOT_LOADED


def geometry_field_reason(summary: "AssetMetadataSummary", *, field_name: str) -> str:
    """Placeholder when a mesh geometry field is missing but the reason is known."""
    from meshcorral.services.metadata.geometry_metadata import is_mesh_geometry_extension

    _ = field_name
    if not is_mesh_geometry_extension(summary.ext):
        return FIELD_UNSUPPORTED
    if (summary.deferred_reason or "").strip():
        return FIELD_DEFERRED
    src = (summary.metadata_source or "").strip().lower()
    if src == "deferred":
        return FIELD_DEFERRED
    if src == "unavailable":
        return FIELD_UNAVAILABLE
    if src == "render" and summary.has_geometry_fields():
        return METADATA_STATUS_READY
    cache = (summary.cache_status or "").strip().lower()
    if "ready" in cache or "indexed" in cache:
        return METADATA_PREVIEW_READY_NOT_LOADED
    return FIELD_NOT_LOADED


def format_int_field(value: int | None, *, summary: "AssetMetadataSummary", field_name: str) -> str:
    if value is None:
        return geometry_field_reason(summary, field_name=field_name)
    return f"{int(value):,}"


def format_dimensions_field(
    dimensions_mm: tuple[float, float, float] | None,
    *,
    summary: "AssetMetadataSummary",
) -> str:
    if dimensions_mm is None:
        return geometry_field_reason(summary, field_name="dimensions")
    x, y, z = dimensions_mm
    return f"{x:.2f} × {y:.2f} × {z:.2f} mm"


def format_watertight_field(value: bool | None, *, summary: "AssetMetadataSummary") -> str:
    if value is None:
        return geometry_field_reason(summary, field_name="watertight")
    return "Yes" if value else "No"


def format_mesh_density_field(value: float | None, *, summary: "AssetMetadataSummary") -> str:
    if value is None:
        return geometry_field_reason(summary, field_name="mesh_density")
    return f"{float(value):.4f} faces/mm³"


def metadata_source_user_label(raw: str | None) -> str:
    """Map internal metadata source codes to plain English."""
    key = (raw or "").strip().lower()
    mapping = {
        "live": "Loaded from mesh",
        "render": "From preview render",
        "stat": "From file scan",
        "scan": "From file scan",
        "cache": "From cache",
        "cached": "From cache",
        "deferred": FIELD_DEFERRED,
        "unavailable": FIELD_UNAVAILABLE,
        "pending": FIELD_PENDING,
    }
    return mapping.get(key, (raw or "").strip() or FIELD_NOT_LOADED)


def metadata_unavailable_log_reason(summary: "AssetMetadataSummary") -> str:
    """Short reason string for ``metadata_diagnostics`` logs."""
    if summary.has_geometry_fields():
        return "available"
    if (summary.deferred_reason or "").strip():
        return f"deferred: {summary.deferred_reason}"
    src = (summary.metadata_source or "").strip().lower() or "unknown"
    cache = (summary.cache_status or "").strip()
    if cache:
        return f"{src}; cache={cache}"
    return src
