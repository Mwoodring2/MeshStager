"""Disk cache for rendered preview PNGs (fingerprint: path, size, mtime, mode)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from meshcorral.app.config import USER_DATA_DIR

logger = logging.getLogger(__name__)

RENDER_CACHE_DIR = USER_DATA_DIR / "render_cache"
# Bump when native thumbnail visual style changes (invalidates poor legacy proxy entries).
THUMBNAIL_STYLE_VERSION: str = "thumbnail_style_v4"


@dataclass(frozen=True, slots=True)
class RenderCacheEntry:
    """Resolved cache paths for one fingerprint."""

    png_path: Path
    meta_path: Path
    fingerprint: str


def file_stat_fingerprint(path: Path) -> tuple[int, float]:
    """Return ``(size_bytes, mtime)`` for *path* or raise ``OSError``."""
    st = path.stat()
    return int(st.st_size), float(st.st_mtime)


def build_fingerprint(
    source_path: Path,
    *,
    size_bytes: int,
    mtime: float,
    max_px: int,
    render_mode: str,
) -> str:
    """Stable hash key for render output cache."""
    try:
        normalized = str(source_path.resolve())
    except OSError:
        normalized = str(source_path)
    raw = (
        f"{normalized}|{size_bytes}|{mtime:.6f}|{int(max_px)}|{render_mode}"
        f"|{THUMBNAIL_STYLE_VERSION}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def cache_entry_for_fingerprint(fingerprint: str) -> RenderCacheEntry:
    base = RENDER_CACHE_DIR / fingerprint
    return RenderCacheEntry(
        png_path=base.with_suffix(".png"),
        meta_path=base.with_suffix(".json"),
        fingerprint=fingerprint,
    )


def read_cached_png(
    source_path: Path,
    *,
    size_bytes: int,
    mtime: float,
    max_px: int,
    render_mode: str,
) -> bytes | None:
    """Return cached PNG bytes when fingerprint matches and file exists."""
    fp = build_fingerprint(
        source_path,
        size_bytes=size_bytes,
        mtime=mtime,
        max_px=max_px,
        render_mode=render_mode,
    )
    entry = cache_entry_for_fingerprint(fp)
    try:
        meta = json.loads(entry.meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            return None
        if meta.get("source_path") != str(source_path):
            return None
        if int(meta.get("size_bytes", -1)) != int(size_bytes):
            return None
        if float(meta.get("mtime", -1.0)) != float(mtime):
            return None
        data = entry.png_path.read_bytes()
        if meta.get("png_sha256") != hashlib.sha256(data).hexdigest():
            return None
        return data if data else None
    except (OSError, ValueError, TypeError):
        return None


def clear_render_cache() -> int:
    """
    Delete all files under the render output cache directory.

    Returns the number of files removed.
    """
    if not RENDER_CACHE_DIR.is_dir():
        return 0
    removed = 0
    for path in list(RENDER_CACHE_DIR.iterdir()):
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("Could not delete render cache file %s: %s", path, exc)
    logger.info("Cleared render cache (%d files)", removed)
    return removed


def write_cached_png(
    source_path: Path,
    *,
    size_bytes: int,
    mtime: float,
    max_px: int,
    render_mode: str,
    png_bytes: bytes,
) -> RenderCacheEntry:
    """Write PNG + sidecar metadata for later hits."""
    fp = build_fingerprint(
        source_path,
        size_bytes=size_bytes,
        mtime=mtime,
        max_px=max_px,
        render_mode=render_mode,
    )
    entry = cache_entry_for_fingerprint(fp)
    meta = {
        "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
        "source_path": str(source_path),
        "size_bytes": int(size_bytes),
        "mtime": float(mtime),
        "max_px": int(max_px),
        "render_mode": render_mode,
        "thumbnail_style_version": THUMBNAIL_STYLE_VERSION,
        "fingerprint": fp,
    }
    try:
        entry.png_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(entry.png_path, png_bytes)
        _atomic_write(entry.meta_path, json.dumps(meta, indent=2, sort_keys=True).encode("utf-8"))
    except OSError as exc:
        logger.debug("render cache meta write failed: %s", exc)
    return entry


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
