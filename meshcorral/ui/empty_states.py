"""Reusable empty-state copy and widgets (Prime v1.0 RC)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

# --- Canonical production copy ---
FRESH_LAUNCH = "fresh_launch"
READY_TO_SCAN = "ready_to_scan"
NO_ASSETS_FOUND = "no_assets_found"
NO_MATCHING_RESULTS = "no_matching_results"
NO_SELECTION = "no_selection"
MULTI_SELECTION = "multi_selection"
PREVIEW_UNAVAILABLE = "preview_unavailable"
METADATA_DEFERRED = "metadata_deferred"
SOURCE_UNAVAILABLE = "source_unavailable"
SCAN_CANCELED = "scan_canceled"


@dataclass(frozen=True, slots=True)
class EmptyStateSpec:
    """Title, explanation, and optional next-step line for an empty UI state."""

    title: str
    body: str
    action_text: str = ""
    token: str = ""


_EMPTY_STATE_SPECS: dict[str, EmptyStateSpec] = {
    FRESH_LAUNCH: EmptyStateSpec(
        title="Welcome to MeshStager",
        body="Choose a source folder to scan 3D, DCC, and image assets.",
        action_text="Use Browse… in the left panel, then Scan Source.",
        token=FRESH_LAUNCH,
    ),
    READY_TO_SCAN: EmptyStateSpec(
        title="Ready to scan",
        body="Scan the selected source using the current Asset Mode.",
        action_text="Click Scan Source when you are ready.",
        token=READY_TO_SCAN,
    ),
    NO_ASSETS_FOUND: EmptyStateSpec(
        title="No assets found",
        body="This folder does not contain files supported by the current Asset Mode.",
        action_text="Try another folder, include subfolders, or switch Asset Mode.",
        token=NO_ASSETS_FOUND,
    ),
    NO_MATCHING_RESULTS: EmptyStateSpec(
        title="No matching results",
        body="Try clearing filters or using a broader search.",
        action_text="Use Reset Filters or clear the name search.",
        token=NO_MATCHING_RESULTS,
    ),
    NO_SELECTION: EmptyStateSpec(
        title="Select an asset",
        body="Choose a file to preview metadata, diagnostics, and actions.",
        token=NO_SELECTION,
    ),
    MULTI_SELECTION: EmptyStateSpec(
        title="Multiple assets selected",
        body="Batch actions are available for the selected files.",
        token=MULTI_SELECTION,
    ),
    PREVIEW_UNAVAILABLE: EmptyStateSpec(
        title="Preview unavailable",
        body="This file type does not support preview thumbnails yet.",
        token=PREVIEW_UNAVAILABLE,
    ),
    METADATA_DEFERRED: EmptyStateSpec(
        title="Deferred Preview",
        body="Deferred for speed — preview loads when you browse",
        token=METADATA_DEFERRED,
    ),
    SOURCE_UNAVAILABLE: EmptyStateSpec(
        title="Source unavailable",
        body="The selected folder is offline, moved, or inaccessible.",
        action_text="Use Browse… to choose a folder that is available.",
        token=SOURCE_UNAVAILABLE,
    ),
    SCAN_CANCELED: EmptyStateSpec(
        title="Scan canceled",
        body="No changes were made. Start a new scan when ready.",
        token=SCAN_CANCELED,
    ),
}


def empty_state_spec(kind: str) -> EmptyStateSpec:
    """Return the canonical spec for *kind* (raises KeyError if unknown)."""
    return _EMPTY_STATE_SPECS[kind]


def empty_state_hint_lines(spec: EmptyStateSpec) -> str:
    """Multi-line hint for labels (title, body, optional action)."""
    lines = [spec.title, spec.body]
    if spec.action_text.strip():
        lines.append(spec.action_text.strip())
    return "\n\n".join(lines)


def make_empty_state_widget(
    spec: EmptyStateSpec,
    *,
    parent: QWidget | None = None,
    align_top: bool = True,
) -> QWidget:
    """
    Build a compact empty-state block (title + body + optional action).

    Uses object names ``EmptyStateTitle``, ``EmptyStateBody``, and ``EmptyStateAction``
    for theme styling. Does not add vertical stretch — callers own layout growth.
    """
    wrap = QWidget(parent)
    wrap.setObjectName("EmptyStateBlock")
    wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)

    title = QLabel(spec.title)
    title.setObjectName("EmptyStateTitle")
    title.setWordWrap(True)
    align = (
        Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        if align_top
        else Qt.AlignmentFlag.AlignHCenter
    )
    title.setAlignment(align)

    body = QLabel(spec.body)
    body.setObjectName("EmptyStateBody")
    body.setWordWrap(True)
    body.setAlignment(align)

    lay.addWidget(title)
    lay.addWidget(body)

    if spec.action_text.strip():
        action = QLabel(spec.action_text.strip())
        action.setObjectName("EmptyStateAction")
        action.setWordWrap(True)
        action.setAlignment(align)
        lay.addWidget(action)

    return wrap


def update_empty_state_widget(host: QWidget, spec: EmptyStateSpec) -> None:
    """Update labels inside a widget built by :func:`make_empty_state_widget`."""
    title = host.findChild(QLabel, "EmptyStateTitle")
    body = host.findChild(QLabel, "EmptyStateBody")
    action = host.findChild(QLabel, "EmptyStateAction")
    if title is not None:
        title.setText(spec.title)
    if body is not None:
        body.setText(spec.body)
    if action is not None:
        if spec.action_text.strip():
            action.setText(spec.action_text.strip())
            action.show()
        else:
            action.hide()
