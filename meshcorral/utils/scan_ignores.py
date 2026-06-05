"""
Scan ignore rules for common metadata/junk paths.

Goal: avoid polluting scans and wasting thumbnail work on non-user asset files.
"""

from __future__ import annotations

from pathlib import Path

# Folder names that should never be traversed during recursive scans.
IGNORED_DIRNAMES: frozenset[str] = frozenset(
    {
        ".AppleDouble",
        "$RECYCLE.BIN",
        "System Volume Information",
    }
)

# Exact filenames to ignore anywhere in a scan.
IGNORED_FILENAMES: frozenset[str] = frozenset(
    {
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
    }
)


def is_ignored_dir(path: Path) -> bool:
    """True when *path* is a directory that should be skipped/pruned."""
    try:
        return path.name in IGNORED_DIRNAMES
    except Exception:  # noqa: BLE001
        return True


def is_ignored_file(path: Path) -> bool:
    """True when *path* is a file that should be skipped even if extension matches."""
    try:
        name = path.name
        if name in IGNORED_FILENAMES:
            return True
        # AppleDouble sidecars (macOS): "._<realname>"
        if name.startswith("._"):
            return True
        return False
    except Exception:  # noqa: BLE001
        return True


def is_ignored_path(path: Path) -> bool:
    """True for paths that should not show up as user assets in scans/queues."""
    try:
        if any(part in IGNORED_DIRNAMES for part in path.parts):
            return True
        if is_ignored_file(path):
            return True
        return False
    except Exception:  # noqa: BLE001
        return True

