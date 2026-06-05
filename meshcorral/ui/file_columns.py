"""Column definitions for the file table (headers, display, sort keys)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.utils.datetime_display import format_local_modified_display
from meshcorral.ui.filename_display import truncate_filename
from meshcorral.utils.filesize_display import format_file_size_display


@dataclass(frozen=True)
class ColumnSpec:
    """One table column: label, raw value, display string, optional sort key."""

    key: str
    header: str
    value_getter: Callable[[FileRecord], Any]
    display_formatter: Callable[[Any], str] | None = None
    sort_getter: Callable[[FileRecord], Any] | None = None
    include_in_csv: bool = True


def _identity(value: Any) -> str:
    return "" if value is None else str(value)


def _format_filename(value: Any) -> str:
    return truncate_filename("" if value is None else str(value))


THUMB_COLUMN_KEY: str = "blender_thumb"
THUMB_HEALTH_COLUMN_KEY: str = "thumb_health"


def thumb_column_index() -> int:
    """Column index of the Blender thumbnail column (``FILE_COLUMNS`` order)."""
    for i, c in enumerate(FILE_COLUMNS):
        if c.key == THUMB_COLUMN_KEY:
            return i
    return 0


def thumb_health_column_index() -> int:
    """Column index of the thumbnail health badge column."""
    for i, c in enumerate(FILE_COLUMNS):
        if c.key == THUMB_HEALTH_COLUMN_KEY:
            return i
    return 0


FILE_COLUMNS: list[ColumnSpec] = [
    ColumnSpec(
        key=THUMB_COLUMN_KEY,
        header="Thumb",
        value_getter=lambda record: record.path,
        display_formatter=lambda v: "",
        sort_getter=lambda record: record.name_lower,
        include_in_csv=False,
    ),
    ColumnSpec(
        key=THUMB_HEALTH_COLUMN_KEY,
        header="Thumb status",
        value_getter=lambda record: record.path,
        display_formatter=lambda v: "",
        sort_getter=None,
        include_in_csv=False,
    ),
    ColumnSpec(
        key="name",
        header="Name",
        value_getter=lambda record: record.name,
        display_formatter=_format_filename,
        sort_getter=lambda record: record.name_lower,
    ),
    ColumnSpec(
        key="extension",
        header="Ext",
        value_getter=lambda record: record.extension,
        display_formatter=_identity,
        sort_getter=lambda record: record.extension.lower(),
    ),
    ColumnSpec(
        key="asset_family",
        header="Type",
        value_getter=lambda record: record.asset_family,
        display_formatter=_identity,
        sort_getter=lambda record: record.asset_family.lower(),
    ),
    ColumnSpec(
        key="parent_folder",
        header="Folder",
        value_getter=lambda record: record.parent_folder,
        display_formatter=_identity,
        sort_getter=lambda record: record.parent_folder.lower(),
    ),
    ColumnSpec(
        key="path",
        header="Path",
        value_getter=lambda record: str(record.path),
        display_formatter=_identity,
        sort_getter=lambda record: str(record.path).lower(),
    ),
    ColumnSpec(
        key="size_bytes",
        header="Size",
        value_getter=lambda record: record.size_bytes,
        display_formatter=format_file_size_display,
        sort_getter=lambda record: record.size_bytes,
    ),
    ColumnSpec(
        key="modified_time",
        header="Modified",
        value_getter=lambda record: record.modified_time,
        display_formatter=format_local_modified_display,
        sort_getter=lambda record: record.modified_time,
    ),
]


RICH_METADATA_EXPORT_HEADERS: tuple[str, ...] = (
    "Dimensions (mm)",
    "Faces",
    "Vertices",
    "Watertight",
    "Mesh Density",
    "Archive Members",
    "Metadata Source",
    "Cache Status",
)


def export_headers() -> list[str]:
    """
    Return CSV header labels: table columns plus optional rich metadata columns.

    Use with :func:`export_row_for_record` so export stays aligned with the UI.
    """
    base = [column.header for column in FILE_COLUMNS if column.include_in_csv]
    return base + list(RICH_METADATA_EXPORT_HEADERS)


def rich_metadata_export_cells(summary: AssetMetadataSummary | None) -> list[str]:
    """CSV cells for rich metadata (empty when *summary* is missing)."""
    if summary is None:
        return [""] * len(RICH_METADATA_EXPORT_HEADERS)
    return [
        summary.dimensions_display(),
        summary.face_count_display(),
        summary.vertex_count_display(),
        summary.watertight_display(),
        summary.mesh_density_display(),
        summary.archive_members_display(),
        summary.metadata_source_display(),
        summary.cache_status_display(),
    ]


def export_row_for_record(
    record: FileRecord,
    summary: AssetMetadataSummary | None = None,
) -> list[str]:
    """
    Return one CSV row using the same display formatting as the table.

    Size and modified values match what the user sees (not raw bytes or epoch).
    """
    row: list[str] = []
    for column in FILE_COLUMNS:
        if not column.include_in_csv:
            continue
        value = column.value_getter(record)
        if column.display_formatter is not None:
            row.append(column.display_formatter(value))
        else:
            row.append("" if value is None else str(value))
    row.extend(rich_metadata_export_cells(summary))
    return row
