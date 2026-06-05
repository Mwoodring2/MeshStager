"""One-time migration from legacy Roundup branding paths to MeshStager.

Preserves QSettings, local caches, tags, favorites, bridge outputs, and logs
without changing database schemas or file formats.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

_MIGRATION_MARKER_KEY = "branding/migrated_from_roundup"


def _local_app_data_root() -> Path:
    import os

    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return Path.home()


def legacy_user_data_dir(legacy_app_name: str) -> Path:
    """Return the pre-rebrand per-user data directory."""
    if legacy_app_name:
        root = _local_app_data_root()
        if root.name:  # pragma: no cover - defensive
            return root / legacy_app_name
    return _local_app_data_root() / "Roundup"


def resolve_user_data_dir(app_name: str, legacy_app_name: str) -> Path:
    """
    Resolve the active user data directory, migrating legacy Roundup data once.

    Preferred order:
    1. Existing MeshStager directory (possibly after migration)
    2. Legacy Roundup directory (copied forward, not deleted)
    3. Fresh MeshStager directory
    """
    root = _local_app_data_root()
    current = root / app_name
    legacy = root / legacy_app_name

    if legacy.is_dir() and legacy_app_name != app_name:
        if not current.is_dir():
            logger.info(
                "Migrating user data directory: %s -> %s",
                legacy,
                current,
            )
            shutil.copytree(legacy, current, dirs_exist_ok=False)
        else:
            _merge_missing_tree(legacy, current)

    current.mkdir(parents=True, exist_ok=True)
    return current


def _merge_missing_tree(source: Path, destination: Path) -> None:
    """Copy files and subdirectories from *source* that are absent in *destination*."""
    for item in source.rglob("*"):
        rel = item.relative_to(source)
        target = destination / rel
        if target.exists():
            continue
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def migrate_qsettings_if_needed(
    *,
    org_name: str,
    app_name: str,
    legacy_app_name: str,
) -> None:
    """
    Copy QSettings from the legacy Roundup scope into MeshStager when needed.

    Legacy settings remain on disk for rollback; MeshStager reads the new scope.
    """
    if not legacy_app_name or legacy_app_name == app_name:
        return

    legacy = QSettings(org_name, legacy_app_name)
    current = QSettings(org_name, app_name)

    if current.contains(_MIGRATION_MARKER_KEY):
        return

    legacy_keys = legacy.allKeys()
    if not legacy_keys:
        current.setValue(_MIGRATION_MARKER_KEY, True)
        current.sync()
        return

    migrated = 0
    for key in legacy_keys:
        if not current.contains(key):
            current.setValue(key, legacy.value(key))
            migrated += 1

    current.setValue(_MIGRATION_MARKER_KEY, True)
    current.sync()
    logger.info(
        "Migrated QSettings (%s/%s -> %s/%s): %d keys copied",
        org_name,
        legacy_app_name,
        org_name,
        app_name,
        migrated,
    )


def run_startup_data_migration(
    *,
    org_name: str,
    app_name: str,
    legacy_app_name: str,
) -> Path:
    """Run filesystem and QSettings migration before services initialize."""
    user_dir = resolve_user_data_dir(app_name, legacy_app_name)
    migrate_qsettings_if_needed(
        org_name=org_name,
        app_name=app_name,
        legacy_app_name=legacy_app_name,
    )
    return user_dir
