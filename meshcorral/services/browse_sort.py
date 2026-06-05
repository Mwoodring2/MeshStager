"""
Browse-view sort keys for the MeshStager table and gallery.

Sort modes reorder the filtered working set only; they do not rescan or
regenerate thumbnails.
"""

from __future__ import annotations

from itertools import groupby
from pathlib import Path
from typing import Final

from meshcorral.models.file_record import FileRecord

# Stable mode ids stored in the sort combo ``itemData``.
SORT_NAME_ASC: Final[str] = "name_asc"
SORT_NAME_DESC: Final[str] = "name_desc"
SORT_DATE_DESC: Final[str] = "date_desc"
SORT_DATE_ASC: Final[str] = "date_asc"
SORT_SIZE_DESC: Final[str] = "size_desc"
SORT_SIZE_ASC: Final[str] = "size_asc"
SORT_TYPE_ASC: Final[str] = "type_asc"
SORT_TYPE_DESC: Final[str] = "type_desc"

DEFAULT_SORT_MODE: Final[str] = SORT_NAME_ASC

BROWSE_SORT_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("Name A–Z", SORT_NAME_ASC),
    ("Name Z–A", SORT_NAME_DESC),
    ("Date Newest", SORT_DATE_DESC),
    ("Date Oldest", SORT_DATE_ASC),
    ("Size Largest", SORT_SIZE_DESC),
    ("Size Smallest", SORT_SIZE_ASC),
    ("Type A–Z", SORT_TYPE_ASC),
    ("Type Z–A", SORT_TYPE_DESC),
)


def normalized_extension(record: FileRecord) -> str:
    """Return a lowercase extension including the leading dot, or empty when absent."""
    ext = (record.extension or "").strip().lower()
    if ext:
        return ext
    return Path(record.name).suffix.lower()


def extension_sort_tier(record: FileRecord) -> tuple[int, str, str]:
    """
    Sort key for type modes: extension (case-insensitive), then filename.

    Files without an extension sort last (tier ``1``).
    """
    ext = normalized_extension(record)
    if not ext:
        return (1, "", record.name_lower)
    return (0, ext, record.name_lower)


def sort_file_records(records: list[FileRecord], mode: str) -> list[FileRecord]:
    """
    Return a new list sorted by *mode*.

    Sorting is stable and predictable; unknown modes fall back to name A–Z.
    """
    if not records:
        return []
    sort_mode = (mode or DEFAULT_SORT_MODE).strip().lower()

    if sort_mode == SORT_NAME_DESC:
        return sorted(records, key=lambda r: r.name_lower, reverse=True)

    if sort_mode == SORT_DATE_DESC:
        return sorted(records, key=_date_desc_key)

    if sort_mode == SORT_DATE_ASC:
        return sorted(records, key=_date_asc_key)

    if sort_mode == SORT_SIZE_DESC:
        return sorted(records, key=_size_desc_key)

    if sort_mode == SORT_SIZE_ASC:
        return sorted(records, key=_size_asc_key)

    if sort_mode == SORT_TYPE_ASC:
        return sorted(records, key=extension_sort_tier)

    if sort_mode == SORT_TYPE_DESC:
        return _sort_type_descending(records)

    return sorted(records, key=lambda r: r.name_lower)


def _type_group_key(record: FileRecord) -> tuple[int, str]:
    """Group key for type descending (extension tier without filename)."""
    tier = extension_sort_tier(record)
    return (tier[0], tier[1])


def _sort_type_descending(records: list[FileRecord]) -> list[FileRecord]:
    """Type Z–A with filename A–Z inside each extension group; no-extension last."""
    asc = sorted(records, key=extension_sort_tier)
    groups = [list(group) for _key, group in groupby(asc, key=_type_group_key)]
    groups.reverse()
    out: list[FileRecord] = []
    for group in groups:
        out.extend(group)
    return out


def _date_desc_key(record: FileRecord) -> tuple[int, float]:
    """Newest first; missing modified time sorts last."""
    mt = record.modified_time
    if mt is None:
        return (1, 0.0)
    return (0, -float(mt))


def _date_asc_key(record: FileRecord) -> tuple[int, float]:
    """Oldest first; missing modified time sorts last."""
    mt = record.modified_time
    if mt is None:
        return (1, float("inf"))
    return (0, float(mt))


def _size_desc_key(record: FileRecord) -> tuple[int, int]:
    """Largest first; missing size sorts last."""
    size = record.size_bytes
    if size is None:
        return (1, 0)
    return (0, -int(size))


def _size_asc_key(record: FileRecord) -> tuple[int, int]:
    """Smallest first; missing size sorts last."""
    size = record.size_bytes
    if size is None:
        return (1, int(2**31 - 1))
    return (0, int(size))
