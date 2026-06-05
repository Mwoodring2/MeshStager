"""Local staging copies for network/server mesh files before render."""

from __future__ import annotations

import hashlib
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from meshcorral.app.config import USER_DATA_DIR
from meshcorral.services.render.render_cache import file_stat_fingerprint

logger = logging.getLogger(__name__)

STAGING_DIR = USER_DATA_DIR / "render_staging"

# Skip re-copy when staged file matches source fingerprint.
_STAGING_META_SUFFIX = ".staging.json"


@dataclass(frozen=True, slots=True)
class StagingResult:
    """Outcome of staging attempt."""

    local_path: Path
    copied: bool
    elapsed_s: float


def _staging_key(source_path: Path, size_bytes: int, mtime: float) -> str:
    try:
        normalized = str(source_path.resolve())
    except OSError:
        normalized = str(source_path)
    raw = f"{normalized}|{size_bytes}|{mtime:.6f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def clear_staging_cache() -> int:
    """
    Delete all staged copies under ``render_staging``.

    Returns the number of files removed.
    """
    if not STAGING_DIR.is_dir():
        return 0
    removed = 0
    for path in list(STAGING_DIR.iterdir()):
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("Could not delete staging file %s: %s", path, exc)
    logger.info("Cleared staging cache (%d files)", removed)
    return removed


def stage_network_file(source_path: Path) -> StagingResult:
    """
    Copy *source_path* into ``render_staging`` when needed.

    Reuses an existing staged copy when size/mtime match.
    """
    t0 = time.perf_counter()
    src = Path(source_path)
    size_bytes, mtime = file_stat_fingerprint(src)
    key = _staging_key(src, size_bytes, mtime)
    ext = src.suffix.lower() or ".mesh"
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    dest = STAGING_DIR / f"{key}{ext}"
    meta_path = STAGING_DIR / f"{key}{_STAGING_META_SUFFIX}"

    if dest.is_file():
        try:
            if meta_path.is_file():
                import json

                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if (
                    int(meta.get("size_bytes", -1)) == size_bytes
                    and float(meta.get("mtime", -1.0)) == mtime
                    and str(meta.get("source_path")) == str(src)
                ):
                    return StagingResult(
                        local_path=dest,
                        copied=False,
                        elapsed_s=time.perf_counter() - t0,
                    )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    try:
        import json

        meta_path.write_text(
            json.dumps(
                {
                    "source_path": str(src),
                    "size_bytes": size_bytes,
                    "mtime": mtime,
                    "staged_path": str(dest),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("staging meta write failed: %s", exc)

    elapsed = time.perf_counter() - t0
    logger.info("Staged network file %.2f MB in %.2fs -> %s", size_bytes / (1024 * 1024), elapsed, dest)
    return StagingResult(local_path=dest, copied=True, elapsed_s=elapsed)
