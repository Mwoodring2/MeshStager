"""
MeshStager environment check — no project-local database.

User settings, caches, and Blender bridge outputs live under
``%LOCALAPPDATA%\\MeshStager\\`` (migrated from legacy Roundup on first launch).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("init_db")

REPO_ROOT = Path(__file__).resolve().parents[1]


def _user_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA is not set; cannot resolve MeshStager user data path.")
    return Path(local) / "MeshStager"


def main() -> int:
    """Document user data location and ensure base folders exist."""
    logger.info("MeshStager does not use a project-local SQLite database.")
    logger.info("Repo root: %s", REPO_ROOT)

    try:
        data_dir = _user_data_dir()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    subdirs = ("bridge", "bridge/outputs", "logs")
    for name in subdirs:
        target = data_dir / name
        target.mkdir(parents=True, exist_ok=True)
        logger.info("Ensured: %s", target)

    legacy = Path(os.environ.get("LOCALAPPDATA", "")) / "Roundup"
    if legacy.is_dir():
        logger.info("Legacy Roundup data present (migration may run on first launch): %s", legacy)
    else:
        logger.info("No legacy Roundup folder at: %s", legacy)

    logger.info("User data root: %s", data_dir)
    logger.info("Done — launch with launch.bat or: python -m meshcorral.app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
