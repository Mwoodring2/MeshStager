"""Built-in named workspace presets (Prime v1.0 Sprint D)."""

from __future__ import annotations

from meshcorral.app.config import ASSET_MODE_3D, ASSET_MODE_IMAGES
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.layouts.workspace_state import WorkspaceState

PRESET_SCANNING = WorkspaceState(
    browse_view_mode=SettingsService.VIEW_MODE_TABLE,
    thumbnail_pixels=SettingsService.THUMB_PIXELS_96,
    asset_mode=ASSET_MODE_3D,
    restore_search_query=False,
    search_query="",
    category_filter="All",
    extension_filter="All",
    folder_filter="All Folders",
    inspector_tab_index=0,
    main_splitter_sizes=[340, 760, 360],
)

PRESET_REVIEW = WorkspaceState(
    browse_view_mode=SettingsService.VIEW_MODE_GALLERY,
    thumbnail_pixels=SettingsService.THUMB_PIXELS_160,
    asset_mode=ASSET_MODE_3D,
    restore_search_query=False,
    inspector_tab_index=0,
    main_splitter_sizes=[280, 900, 400],
)

PRESET_TEXTURE_AUDIT = WorkspaceState(
    browse_view_mode=SettingsService.VIEW_MODE_GALLERY,
    thumbnail_pixels=SettingsService.THUMB_PIXELS_160,
    asset_mode=ASSET_MODE_IMAGES,
    restore_search_query=False,
    category_filter="All",
    inspector_tab_index=0,
    main_splitter_sizes=[300, 880, 380],
)

PRESET_EXPORT_PREP = WorkspaceState(
    browse_view_mode=SettingsService.VIEW_MODE_TABLE,
    thumbnail_pixels=SettingsService.THUMB_PIXELS_48,
    asset_mode=ASSET_MODE_3D,
    restore_search_query=False,
    sort_column_key="name",
    sort_order="asc",
    inspector_tab_index=3,
    main_splitter_sizes=[300, 820, 420],
)

PRESET_SCULPT_REVIEW = WorkspaceState(
    browse_view_mode=SettingsService.VIEW_MODE_GALLERY,
    thumbnail_pixels=SettingsService.THUMB_PIXELS_256,
    asset_mode=ASSET_MODE_3D,
    restore_search_query=False,
    inspector_tab_index=0,
    main_splitter_sizes=[260, 940, 400],
)

BUILTIN_PRESET_NAMES: tuple[str, ...] = (
    "Scanning",
    "Review",
    "Texture Audit",
    "Export Prep",
    "Sculpt Review",
)

_BUILTIN_MAP: dict[str, WorkspaceState] = {
    "Scanning": PRESET_SCANNING,
    "Review": PRESET_REVIEW,
    "Texture Audit": PRESET_TEXTURE_AUDIT,
    "Export Prep": PRESET_EXPORT_PREP,
    "Sculpt Review": PRESET_SCULPT_REVIEW,
}


def default_workspace_state() -> WorkspaceState:
    """Factory defaults when resetting layout."""
    return WorkspaceState()


def builtin_preset(name: str) -> WorkspaceState | None:
    """Return a copy of a built-in preset by display name."""
    state = _BUILTIN_MAP.get(name.strip())
    if state is None:
        return None
    return WorkspaceState.from_dict(state.to_dict())


def list_builtin_preset_names() -> list[str]:
    """Ordered built-in preset labels."""
    return list(BUILTIN_PRESET_NAMES)
