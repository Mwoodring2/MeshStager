"""In-memory search and filtering for v1."""

from __future__ import annotations

from collections.abc import Callable

from meshcorral.app.config import FILE_TYPE_CATEGORIES, file_type_category_map_for_asset_mode
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import (
    THUMB_FILTER_ALL,
    ThumbHealth,
    thumb_health_matches_filter,
)
from meshcorral.services.favorites.favorite_filter import FAVORITE_FILTER_ALL, FAVORITE_FILTER_ONLY


def filter_records(
    records: list[FileRecord],
    search_text: str = "",
    extension_filter: str = "All",
    folder_filter: str = "All Folders",
    category_filter: str = "All",
    asset_mode: str | None = None,
    thumb_health_filter: str = THUMB_FILTER_ALL,
    thumb_health_for: Callable[[FileRecord], ThumbHealth] | None = None,
    favorite_filter: str = FAVORITE_FILTER_ALL,
    is_favorite_for: Callable[[FileRecord], bool] | None = None,
    collection_filter: Callable[[FileRecord], bool] | None = None,
    housekeeping_filter: Callable[[FileRecord], bool] | None = None,
) -> list[FileRecord]:
    """
    Filter by category, extension, parent folder name, optional name search text,
    and optional Blender thumbnail health (when *thumb_health_for* is provided).
    """
    search_text = search_text.strip().lower()
    selected_folder = folder_filter.strip()

    if asset_mode is None:
        allowed_extensions = FILE_TYPE_CATEGORIES.get(
            category_filter, FILE_TYPE_CATEGORIES["All"]
        )
    else:
        m = file_type_category_map_for_asset_mode(asset_mode)
        allowed_extensions = m.get(category_filter, m["All"])

    filtered: list[FileRecord] = []
    for record in records:
        if housekeeping_filter is not None and not housekeeping_filter(record):
            continue

        if collection_filter is not None and not collection_filter(record):
            continue

        if record.extension not in allowed_extensions:
            continue

        if extension_filter != "All" and record.extension != extension_filter.lower():
            continue

        if selected_folder != "All Folders" and record.parent_folder != selected_folder:
            continue

        if search_text and search_text not in record.name_lower:
            continue

        if thumb_health_for is not None and thumb_health_filter != THUMB_FILTER_ALL:
            if not thumb_health_matches_filter(
                thumb_health_filter, thumb_health_for(record)
            ):
                continue

        if (
            favorite_filter == FAVORITE_FILTER_ONLY
            and is_favorite_for is not None
            and not is_favorite_for(record)
        ):
            continue

        filtered.append(record)

    return filtered
