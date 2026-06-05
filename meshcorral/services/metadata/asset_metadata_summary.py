"""Lightweight metadata summary for inspector, export, and search."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AssetMetadataSummary:
    """
    Stable metadata snapshot for one asset path.

    Geometry fields may be ``None`` when deferred, unavailable, or not applicable.
    """

    path: Path
    ext: str
    dimensions_mm: tuple[float, float, float] | None = None
    face_count: int | None = None
    vertex_count: int | None = None
    watertight: bool | None = None
    mesh_density: float | None = None
    archive_member_count: int | None = None
    thumbnail_render_profile: str | None = None
    metadata_source: str | None = None
    cache_status: str | None = None
    deferred_reason: str | None = None

    def has_geometry_fields(self) -> bool:
        """True when at least one mesh geometry field is populated."""
        return (
            self.dimensions_mm is not None
            or self.face_count is not None
            or self.vertex_count is not None
            or self.watertight is not None
            or self.mesh_density is not None
        )

    def dimensions_display(self) -> str:
        """Bounding box extents as millimeters (STL/OBJ assumed mm)."""
        from meshcorral.services.metadata.metadata_display_copy import format_dimensions_field

        return format_dimensions_field(self.dimensions_mm, summary=self)

    def face_count_display(self) -> str:
        """Formatted face count or plain-English reason."""
        from meshcorral.services.metadata.metadata_display_copy import format_int_field

        return format_int_field(self.face_count, summary=self, field_name="faces")

    def vertex_count_display(self) -> str:
        """Formatted vertex count or plain-English reason."""
        from meshcorral.services.metadata.metadata_display_copy import format_int_field

        return format_int_field(self.vertex_count, summary=self, field_name="vertices")

    def watertight_display(self) -> str:
        """Yes / No / reason when unknown."""
        from meshcorral.services.metadata.metadata_display_copy import format_watertight_field

        return format_watertight_field(self.watertight, summary=self)

    def mesh_density_display(self) -> str:
        """Faces per mm³ when computable, else reason."""
        from meshcorral.services.metadata.metadata_display_copy import format_mesh_density_field

        return format_mesh_density_field(self.mesh_density, summary=self)

    def geometry_diagnostics_display(self) -> str:
        """
        One-line mesh/geometry summary for inspector Diagnostics.

        Never uses thumbnail-health labels (A5.3 / Prime v1.0 RC F-01).
        """
        from meshcorral.services.metadata.geometry_metadata import is_mesh_geometry_extension
        from meshcorral.services.metadata.metadata_display_copy import (
            METADATA_STATUS_DEFERRED,
            METADATA_STATUS_NOT_LOADED,
            METADATA_STATUS_UNSUPPORTED,
        )

        if not is_mesh_geometry_extension(self.ext):
            return METADATA_STATUS_UNSUPPORTED

        if (self.deferred_reason or "").strip():
            return METADATA_STATUS_DEFERRED

        parts: list[str] = []
        if self.watertight is not None:
            parts.append("Watertight" if self.watertight else "Non-watertight")
        if self.vertex_count is not None:
            parts.append(f"{self.vertex_count:,} verts")
        if self.face_count is not None:
            parts.append(f"{self.face_count:,} faces")
        if self.mesh_density is not None:
            parts.append(f"Density {self.mesh_density:.4f}")

        if not parts and self.dimensions_mm is not None:
            return self.dimensions_display()

        if parts:
            return " · ".join(parts)

        return METADATA_STATUS_NOT_LOADED

    def archive_members_display(self) -> str:
        """Archive member count label."""
        if self.archive_member_count is None:
            return "—"
        n = self.archive_member_count
        return f"{n:,} member{'s' if n != 1 else ''}"

    def metadata_status_display(self) -> str:
        """Plain-English metadata readiness (separate from preview/thumbnail state)."""
        from meshcorral.services.metadata.metadata_display_copy import metadata_status_label

        return metadata_status_label(self)

    def metadata_source_display(self) -> str:
        """Human-readable metadata provenance."""
        from meshcorral.services.metadata.metadata_display_copy import metadata_source_user_label

        return metadata_source_user_label(self.metadata_source)

    def cache_status_display(self) -> str:
        """Cache / deferral state for diagnostics."""
        return (self.cache_status or "").strip() or "—"

    def thumbnail_render_profile_display(self) -> str:
        """Thumbnail renderer profile label."""
        return (self.thumbnail_render_profile or "").strip() or "—"

    def copy_block_lines(self) -> list[str]:
        """Lines for clipboard export of rich metadata."""
        lines = [
            f"Metadata status: {self.metadata_status_display()}",
            f"Dimensions: {self.dimensions_display()}",
            f"Faces: {self.face_count_display()}",
            f"Vertices: {self.vertex_count_display()}",
            f"Watertight: {self.watertight_display()}",
            f"Mesh density: {self.mesh_density_display()}",
            f"Archive members: {self.archive_members_display()}",
            f"Metadata source: {self.metadata_source_display()}",
            f"Cache status: {self.cache_status_display()}",
        ]
        if self.thumbnail_render_profile:
            lines.append(f"Thumbnail profile: {self.thumbnail_render_profile}")
        return lines

    def with_updates(self, **kwargs: object) -> AssetMetadataSummary:
        """Return a copy with replaced fields (immutable update)."""
        return replace(self, **kwargs)
