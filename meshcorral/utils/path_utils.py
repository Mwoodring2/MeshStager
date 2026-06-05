"""Path utilities for Roundup (Windows-first)."""

from __future__ import annotations

from pathlib import Path


def safe_resolve_path(path: Path) -> Path:
    """Normalize ``~``, ``.``, and ``..`` without requiring the path to exist.

    Used so planning, conflicts, and same-path checks agree with execution.
    """
    try:
        return path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return path.expanduser()


def normalize_path(value: str) -> Path:
    """Convert a user-entered path string to a normalized ``Path``."""
    text = (value or "").strip().strip('"').rstrip("/\\")
    if not text:
        raise ValueError("Path is empty.")
    try:
        return safe_resolve_path(Path(text))
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"Invalid path: {value}") from exc


def is_within_directory(child: Path, parent: Path) -> bool:
    """Return True if child is within parent (best-effort, no filesystem access)."""
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
        _ = child_resolved.relative_to(parent_resolved)
        return True
    except Exception:
        return False


def build_flat_destination_path(source_file: Path, destination_dir: Path) -> Path:
    """Build the destination path for a "flat move" (no subfolder recreation).

    v1 behavior is intentionally simple and predictable:
    - destination is always `destination_dir / source_file.name`
    """
    if not source_file.name:
        raise ValueError("Source file name is empty.")
    return destination_dir / source_file.name

