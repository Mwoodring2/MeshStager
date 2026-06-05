"""Prime v1.0 — view models for the tabbed asset inspector."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QPixmap

_NOT_AVAILABLE = "Not available"


@dataclass(frozen=True, slots=True)
class InspectorSingleDetail:
    """Snapshot of one selected asset for all inspector tabs."""

    name: str
    path_str: str
    extension: str
    size_display: str
    modified_display: str
    folder_display: str
    asset_mode_display: str
    metadata_source_display: str
    tags: str
    metadata_block: str
    metadata_copy_text: str
    pixmap: QPixmap | None
    missing_file: bool
    can_generate_blender_thumbnail: bool
    has_blender_thumbnail: bool
    blender_thumbnail_path: str
    preview_kind: str = ""
    preview_subline: str = ""
    preview_blocked_message: str | None = None
    thumb_status_display: str = _NOT_AVAILABLE
    renderer_profile_display: str = _NOT_AVAILABLE
    mesh_health_display: str = _NOT_AVAILABLE
    archive_member_count_display: str = _NOT_AVAILABLE
    unsupported_reason_display: str = _NOT_AVAILABLE
    cache_status_display: str = _NOT_AVAILABLE
    thumbnail_state_display: str = _NOT_AVAILABLE
    dimensions_display: str = _NOT_AVAILABLE
    face_count_display: str = _NOT_AVAILABLE
    vertex_count_display: str = _NOT_AVAILABLE
    watertight_display: str = _NOT_AVAILABLE
    mesh_density_display: str = _NOT_AVAILABLE
    archive_members_rich_display: str = _NOT_AVAILABLE
    metadata_cache_display: str = _NOT_AVAILABLE
    deferred_reason_display: str = ""
    preview_thumb_headline: str | None = None
    preview_thumb_body: str | None = None
    preview_show_retry_thumbnail: bool | None = None
    preview_retry_button_label: str | None = None
    thumbnail_backend_display: str = ""
    thumbnail_failure_reason_display: str = ""
    thumbnail_fallback_reason_display: str = ""
    thumbnail_suggested_action_display: str = ""
    filename_full: str = ""

    def extension_badge(self) -> str:
        """Short type badge for the preview header."""
        ext = (self.extension or "").strip()
        if not ext or ext == "—":
            return "FILE"
        return ext.upper()
