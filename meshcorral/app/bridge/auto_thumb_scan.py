"""
Helpers to select .stl / .obj records and apply a per-scan queue cap (auto thumbnails).

No I/O: pure functions for tests and a thin orchestration path from the main window.
"""

from __future__ import annotations

from collections.abc import Sequence

from meshcorral.models.file_record import FileRecord
from meshcorral.services.settings_service import SettingsService
from meshcorral.utils.scan_ignores import is_ignored_path

# Auto thumbnails for these mesh types (scan uses lowercase extensions).
# Native thumbnails cover a subset (.stl/.obj/.ply/.glb/.gltf); Blender remains optional fallback.
_AUTO_THUMB_EXTENSIONS: frozenset[str] = frozenset({".stl", ".obj", ".ply", ".glb", ".gltf", ".fbx"})

def is_auto_thumbnail_extension(record: FileRecord) -> bool:
    """True if the record is a .stl or .obj file (case-insensitive)."""
    if record.extension.lower() not in _AUTO_THUMB_EXTENSIONS:
        return False
    return not is_ignored_path(record.path)


def filter_auto_thumbnail_records(records: Sequence[FileRecord]) -> list[FileRecord]:
    """Return only .stl / .obj rows (preserving order)."""
    return [r for r in records if is_auto_thumbnail_extension(r)]


def take_with_cap(items: list[FileRecord], cap: int) -> list[FileRecord]:
    """
    Return at most *cap* items from the start of *items*.

    ``cap == 0`` (see :attr:`SettingsService.CAP_AUTO_THUMB_UNLIMITED`) means no limit.
    """
    if cap == SettingsService.CAP_AUTO_THUMB_UNLIMITED:
        return list(items)
    if cap < 0:
        return []
    return list(items)[: min(cap, len(items))]
