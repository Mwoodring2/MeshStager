"""Thumbnail coverage labels for Blender bridge output (no database)."""

from __future__ import annotations

from enum import Enum

from meshcorral.models.file_record import FileRecord

# Formats for which Roundup can attempt thumbnail generation (native or optional Blender bridge).
THUMB_MESH_EXTENSIONS: frozenset[str] = frozenset({".stl", ".obj", ".ply", ".glb", ".gltf", ".fbx"})

THUMB_FILTER_ALL: str = "All"
THUMB_FILTER_HAS: str = "Has thumbnails"
THUMB_FILTER_MISSING: str = "Missing thumbnails"
THUMB_FILTER_FAILED: str = "Failed thumbnail jobs"
THUMB_FILTER_UNSUPPORTED: str = "Unsupported"

THUMB_FILTER_CHOICES: tuple[str, ...] = (
    THUMB_FILTER_ALL,
    THUMB_FILTER_HAS,
    THUMB_FILTER_MISSING,
    THUMB_FILTER_FAILED,
    THUMB_FILTER_UNSUPPORTED,
)


class ThumbHealth(str, Enum):
    """Indexed Blender thumbnail state for a file row."""

    HAS_THUMBNAIL = "has_thumbnail"
    PENDING = "pending"
    MISSING_THUMBNAIL = "missing_thumbnail"
    FAILED_THUMBNAIL = "failed_thumbnail"
    UNSUPPORTED = "unsupported"

    def display_label(self) -> str:
        """Short human-readable label for tooltips and UI copy."""
        return _DISPLAY_LABELS[self]

    @property
    def sort_value(self) -> int:
        """Stable ascending order for the table (health column sort role)."""
        return _SORT_RANK[self]


_DISPLAY_LABELS: dict[ThumbHealth, str] = {
    ThumbHealth.HAS_THUMBNAIL: "Thumbnail ready",
    ThumbHealth.PENDING: "Thumbnail pending",
    ThumbHealth.MISSING_THUMBNAIL: "Thumbnail not generated yet",
    ThumbHealth.FAILED_THUMBNAIL: "Thumbnail failed",
    ThumbHealth.UNSUPPORTED: "Thumbnail not supported",
}

_SORT_RANK: dict[ThumbHealth, int] = {
    ThumbHealth.HAS_THUMBNAIL: 0,
    ThumbHealth.PENDING: 1,
    ThumbHealth.MISSING_THUMBNAIL: 2,
    ThumbHealth.FAILED_THUMBNAIL: 3,
    ThumbHealth.UNSUPPORTED: 4,
}


def thumb_health_matches_filter(filter_label: str, health: ThumbHealth) -> bool:
    """
    Return True if *health* should remain visible when the user selects *filter_label*.

    Unknown filter labels behave like ``All`` (nothing removed).
    """
    if filter_label == THUMB_FILTER_ALL:
        return True
    if health == ThumbHealth.PENDING:
        return False
    want = _FILTER_TO_HEALTH.get(filter_label)
    if want is None:
        return True
    return health == want


_FILTER_TO_HEALTH: dict[str, ThumbHealth] = {
    THUMB_FILTER_HAS: ThumbHealth.HAS_THUMBNAIL,
    THUMB_FILTER_MISSING: ThumbHealth.MISSING_THUMBNAIL,
    THUMB_FILTER_FAILED: ThumbHealth.FAILED_THUMBNAIL,
    THUMB_FILTER_UNSUPPORTED: ThumbHealth.UNSUPPORTED,
}


def classify_thumb_health(
    *,
    has_resolved_thumbnail: bool,
    has_recorded_failure: bool,
    record: FileRecord,
) -> ThumbHealth:
    """
    Derive :class:`ThumbHealth` from index state and file extension.

    Order: on-disk thumbnail wins; then last failed bridge job; then supported mesh
    without thumb; else unsupported for this Blender thumbnail path.
    """
    if has_resolved_thumbnail:
        return ThumbHealth.HAS_THUMBNAIL
    if has_recorded_failure:
        return ThumbHealth.FAILED_THUMBNAIL
    ext = record.extension.lower()
    if ext in THUMB_MESH_EXTENSIONS:
        return ThumbHealth.MISSING_THUMBNAIL
    return ThumbHealth.UNSUPPORTED
