"""Controlled mini-mesh warm-up for RC2 benchmark (not user archive files)."""

from __future__ import annotations

import logging
from pathlib import Path

from meshcorral.app.config import USER_DATA_DIR

logger = logging.getLogger(__name__)

WARMUP_NOTE = (
    "Warm-up uses an internal mini STL (module import + tiny mesh) and is excluded from file averages."
)

# Valid ASCII STL — one triangle, sub‑KB (not a production archive mesh).
INTERNAL_WARMUP_STL_BYTES = (
    b"solid meshstager_benchmark_warmup\n"
    b"  facet normal 0 0 1\n    outer loop\n"
    b"      vertex 0 0 0\n      vertex 1 0 0\n      vertex 0 1 0\n"
    b"    endloop\n  endfacet\nendsolid meshstager_benchmark_warmup\n"
)

INTERNAL_WARMUP_DIR = USER_DATA_DIR / "benchmark"
INTERNAL_WARMUP_FILENAME = "internal_warmup.stl"


def internal_warmup_stl_path() -> Path:
    """
    Return path to the internal mini STL, creating or refreshing it under user data.

    Always under ``%LOCALAPPDATA%\\MeshStager\\benchmark\\`` — never a user scan folder.
    """
    INTERNAL_WARMUP_DIR.mkdir(parents=True, exist_ok=True)
    path = INTERNAL_WARMUP_DIR / INTERNAL_WARMUP_FILENAME
    try:
        if path.is_file():
            existing = path.read_bytes()
            if existing == INTERNAL_WARMUP_STL_BYTES:
                return path
    except OSError as exc:
        logger.debug("Could not read existing warm-up STL: %s", exc)
    path.write_bytes(INTERNAL_WARMUP_STL_BYTES)
    logger.info("Internal benchmark warm-up mesh: %s (%d bytes)", path, len(INTERNAL_WARMUP_STL_BYTES))
    return path


def resolve_warmup_mesh_path(
    *,
    user_mesh: Path | None = None,
    allow_user_mesh: bool = False,
) -> Path:
    """
    Pick the warm-up mesh path.

    Default: internal mini STL only.
    When *allow_user_mesh* is True and *user_mesh* is a readable file, use that path instead.
    """
    if allow_user_mesh and user_mesh is not None:
        candidate = Path(user_mesh)
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                logger.warning(
                    "Warm-up using user file (not recommended for cold-start reporting): %s",
                    candidate,
                )
                return candidate
        except OSError as exc:
            logger.warning("User warm-up path unusable (%s); using internal mini STL", exc)
    return internal_warmup_stl_path()
