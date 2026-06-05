"""Stable workspace state extracted from the main window (not raw widgets)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

WORKSPACE_SCHEMA_VERSION = 1


@dataclass
class WorkspaceState:
    """
    Serializable UI workflow state for Roundup.

    Field names are stable across UI refactors; widgets are never persisted directly.
    """

    schema_version: int = WORKSPACE_SCHEMA_VERSION
    browse_view_mode: str = "table"
    thumbnail_pixels: int = 48
    asset_mode: str = "3d"
    search_query: str = ""
    restore_search_query: bool = True
    extension_filter: str = "All"
    category_filter: str = "All"
    folder_filter: str = "All Folders"
    thumb_health_filter: str = "All"
    include_subfolders: bool = True
    inspector_tab_index: int = 0
    main_splitter_sizes: list[int] = field(default_factory=lambda: [310, 720, 418])
    table_column_widths: dict[str, int] = field(default_factory=dict)
    hidden_column_keys: list[str] = field(default_factory=list)
    sort_column_key: str = "name"
    sort_order: str = "asc"

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WorkspaceState:
        """Build from a dict; unknown keys are ignored."""
        if not raw:
            return cls()
        version = int(raw.get("schema_version", WORKSPACE_SCHEMA_VERSION))
        splitter = raw.get("main_splitter_sizes", [310, 720, 418])
        if not isinstance(splitter, list):
            splitter = [310, 720, 418]
        sizes: list[int] = []
        for x in splitter:
            try:
                sizes.append(int(x))
            except (TypeError, ValueError):
                continue
        if len(sizes) < 3:
            sizes = [310, 720, 418]

        widths_raw = raw.get("table_column_widths", {})
        widths: dict[str, int] = {}
        if isinstance(widths_raw, dict):
            for key, val in widths_raw.items():
                try:
                    widths[str(key)] = int(val)
                except (TypeError, ValueError):
                    continue

        hidden = raw.get("hidden_column_keys", [])
        hidden_keys = [str(k) for k in hidden] if isinstance(hidden, list) else []

        return cls(
            schema_version=version,
            browse_view_mode=str(raw.get("browse_view_mode", "table")),
            thumbnail_pixels=int(raw.get("thumbnail_pixels", 48)),
            asset_mode=str(raw.get("asset_mode", "3d")),
            search_query=str(raw.get("search_query", "")),
            restore_search_query=bool(raw.get("restore_search_query", True)),
            extension_filter=str(raw.get("extension_filter", "All")),
            category_filter=str(raw.get("category_filter", "All")),
            folder_filter=str(raw.get("folder_filter", "All Folders")),
            thumb_health_filter=str(raw.get("thumb_health_filter", "All")),
            include_subfolders=bool(raw.get("include_subfolders", True)),
            inspector_tab_index=int(raw.get("inspector_tab_index", 0)),
            main_splitter_sizes=sizes[:3],
            table_column_widths=widths,
            hidden_column_keys=hidden_keys,
            sort_column_key=str(raw.get("sort_column_key", "name")),
            sort_order=str(raw.get("sort_order", "asc")),
        )

    def to_json(self) -> str:
        """Serialize to JSON text for QSettings storage."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> WorkspaceState:
        """Parse JSON; invalid input yields defaults."""
        if not (text or "").strip():
            return cls()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(data)
