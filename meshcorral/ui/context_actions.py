"""Context-menu action definitions for the file table (single spec list)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextActionSpec:
    """One context-menu entry: label, handler method name, enable rules."""

    key: str
    label: str
    handler_name: str
    requires_selection: bool = True
    requires_source: bool = False
    separator_before: bool = False
    # If set, selected row count must be within [min, max] (inclusive).
    selection_count_min: int | None = None
    selection_count_max: int | None = None


FILE_CONTEXT_ACTIONS: list[ContextActionSpec] = [
    ContextActionSpec(
        key="open_file",
        label="Open in Default App",
        handler_name="_open_selected_file",
        requires_selection=True,
        requires_source=True,
    ),
    ContextActionSpec(
        key="open_in_preferred_dcc",
        label="Open in Preferred DCC",
        handler_name="_open_in_preferred_dcc",
        requires_selection=True,
        requires_source=True,
        selection_count_min=1,
        selection_count_max=1,
    ),
    ContextActionSpec(
        key="open_in_blender",
        label="Open in Blender",
        handler_name="_open_in_blender",
        requires_selection=True,
        requires_source=True,
        selection_count_min=1,
        selection_count_max=1,
    ),
    ContextActionSpec(
        key="open_in_maya",
        label="Open in Maya",
        handler_name="_open_in_maya",
        requires_selection=True,
        requires_source=True,
        selection_count_min=1,
        selection_count_max=1,
    ),
    ContextActionSpec(
        key="reveal_in_explorer",
        label="Reveal in Explorer",
        handler_name="_reveal_selected",
        requires_selection=True,
        requires_source=True,
    ),
    ContextActionSpec(
        key="copy_selected_path",
        label="Copy Selected Path",
        handler_name="_copy_selected_path",
        requires_selection=True,
        requires_source=True,
    ),
    ContextActionSpec(
        key="open_thumb_job_folder",
        label="Open Failed Thumbnail Job Folder",
        handler_name="_open_thumb_job_folder",
        requires_selection=True,
        requires_source=True,
        separator_before=True,
        selection_count_min=1,
        selection_count_max=1,
    ),
    ContextActionSpec(
        key="blender_thumbnail",
        label="Generate Thumbnail (Blender)…",
        handler_name="_generate_blender_thumbnail",
        requires_selection=True,
        requires_source=True,
        selection_count_min=1,
        selection_count_max=1,
    ),
    ContextActionSpec(
        key="blender_thumbnails_batch",
        label="Queue Blender Thumbnails for Selected",
        handler_name="_queue_blender_thumbnails_selected",
        requires_selection=True,
        requires_source=True,
        selection_count_min=2,
        selection_count_max=None,
    ),
    ContextActionSpec(
        key="move_selected",
        label="Move Selected",
        handler_name="_move_selected",
        requires_selection=True,
        requires_source=True,
        separator_before=True,
    ),
    ContextActionSpec(
        key="copy_selected_to",
        label="Copy Selected To...",
        handler_name="_copy_selected_files",
        requires_selection=True,
        requires_source=True,
    ),
]
