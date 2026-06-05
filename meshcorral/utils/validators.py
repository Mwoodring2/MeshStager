"""Validation helpers used by UI and services."""

from __future__ import annotations

from pathlib import Path


def require_existing_directory(path: Path, label: str) -> None:
    """Validate that `path` exists and is a directory."""
    if not path.exists():
        raise ValueError(f"{label} does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"{label} is not a directory: {path}")


def require_destination_baseline(path: Path, label: str) -> None:
    """Validate destination for move/copy planning.

    Accepts an existing directory, or a missing path whose parent exists as a
    directory (the destination folder will be created during execution).
    """
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"{label} exists but is not a folder: {path}")
        return
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError(
            f"{label} is not available (folder missing and parent is not a valid directory): {path}"
        )


def require_non_empty_text(value: str, label: str) -> str:
    """Validate and return a non-empty string."""
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{label} is required.")
    return text

